# lambda_function.py
import json
import os
import requests
import logging
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from math import radians, sin, cos, sqrt, atan2

# Import Neptune functions
from neptune_connection import (
    find_nearest_vertices, 
    get_vertex_by_id,
    find_path_between_vertices,
    get_vertex_neighbors,
    test_connection,
    NeptuneConnection
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

# Configuration from environment variables
OPENCAGE_API_KEY = os.environ.get('OPENCAGE_API_KEY', '')
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', '')
GEOCODING_PROVIDER = os.environ.get('GEOCODING_PROVIDER', 'nominatim')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types in JSON serialization"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def log(level: str, message: str, data: Any = None):
    """Simple logging function"""
    if LOG_LEVEL == 'DEBUG' or (LOG_LEVEL == 'INFO' and level in ['INFO', 'ERROR']):
        log_entry = {
            'level': level,
            'message': message
        }
        if data:
            log_entry['data'] = data
        print(json.dumps(log_entry))

def scale_coordinates(latitude: float, longitude: float) -> Tuple[int, int]:
    """
    Scale latitude and longitude by 10^6 to convert to integer format.
    
    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees
    
    Returns:
        Tuple of (scaled_latitude, scaled_longitude) as integers
    
    Example:
        >>> scale_coordinates(45.5152, -122.6784)
        (45515200, -122678400)
    """
    scaled_lat = int(round(latitude * 1_000_000))
    scaled_lon = int(round(longitude * 1_000_000))
    
    logger.info(f"Scaled coordinates: {latitude}, {longitude} -> {scaled_lat}, {scaled_lon}")
    
    return scaled_lat, scaled_lon

def get_coordinates(city: str, state: Optional[str] = None, 
                   country: Optional[str] = None) -> Dict[str, Any]:
    """
    Get coordinates for a city using the configured geocoding provider.
    Now includes scaled integer coordinates.
    """
    # Build query string
    query_parts = [city]
    if state:
        query_parts.append(state)
    if country:
        query_parts.append(country)
    query = ", ".join(query_parts)
    
    logger.info(f"Geocoding query: {query} using provider: {GEOCODING_PROVIDER}")
    
    try:
        if GEOCODING_PROVIDER == 'opencage' and OPENCAGE_API_KEY:
            result = geocode_opencage(query)
        elif GEOCODING_PROVIDER == 'google' and GOOGLE_MAPS_API_KEY:
            result = geocode_google(query)
        else:
            result = geocode_nominatim(query)
        
        # Add scaled coordinates to result
        if 'latitude' in result and 'longitude' in result:
            scaled_lat, scaled_lon = scale_coordinates(
                result['latitude'], 
                result['longitude']
            )
            result['scaled_latitude'] = scaled_lat
            result['scaled_longitude'] = scaled_lon
        
        return result

    except Exception as e:
        logger.error(f"Geocoding error: {str(e)}", exc_info=True)
        return {
            'error': str(e),
            'query': query
        }



# ==================== GEOCODING PROVIDERS ====================

def geocode_opencage(city_name: str) -> Optional[Dict]:
    """
    Get coordinates using OpenCage Geocoding API
    Free tier: 2,500 requests/day
    Docs: https://opencagedata.com/api
    """
    if not OPENCAGE_API_KEY:
        log('INFO', 'OpenCage API key not configured')
        return None
    
    try:
        url = "https://api.opencagedata.com/geocode/v1/json"
        params = {
            'q': city_name,
            'key': OPENCAGE_API_KEY,
            'limit': 1,
            'no_annotations': 0,
            'language': 'en'
        }
        
        log('DEBUG', f'Calling OpenCage API for: {city_name}')
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('results'):
            result = data['results'][0]
            geometry = result['geometry']
            components = result['components']
            
            coord_data = {
                "success": True,
                "city": city_name,
                "latitude": geometry['lat'],
                "longitude": geometry['lng'],
                "formatted_address": result['formatted'],
                "country": components.get('country', 'Unknown'),
                "country_code": components.get('country_code', '').upper(),
                "state": components.get('state', ''),
                "confidence": result.get('confidence', 0),
                "timezone": result.get('annotations', {}).get('timezone', {}).get('name', ''),
                "source": "OpenCage Geocoding API",
                "bounds": result.get('bounds', {}),
            }
            
            log('INFO', f'OpenCage: Found coordinates for {city_name}', {
                'lat': coord_data['latitude'],
                'lng': coord_data['longitude']
            })
            
            return coord_data
        else:
            log('INFO', f'OpenCage: No results found for {city_name}')
            return {
                "success": False,
                "city": city_name,
                "error": "No results found",
                "source": "OpenCage Geocoding API"
            }
            
    except requests.exceptions.RequestException as e:
        log('ERROR', f'OpenCage API request error: {str(e)}')
        return None
    except Exception as e:
        log('ERROR', f'OpenCage processing error: {str(e)}')
        return None

def geocode_google(city_name: str) -> Optional[Dict]:
    """
    Get coordinates using Google Maps Geocoding API
    Pricing: $5 per 1000 requests (after $200 monthly credit)
    Docs: https://developers.google.com/maps/documentation/geocoding
    """
    if not GOOGLE_MAPS_API_KEY:
        log('INFO', 'Google Maps API key not configured')
        return None
    
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            'address': city_name,
            'key': GOOGLE_MAPS_API_KEY
        }
        
        log('DEBUG', f'Calling Google Maps API for: {city_name}')
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data['status'] == 'OK' and data.get('results'):
            result = data['results'][0]
            location = result['geometry']['location']
            
            # Extract address components
            components = {}
            for comp in result.get('address_components', []):
                if comp['types']:
                    components[comp['types'][0]] = comp['long_name']
            
            coord_data = {
                "success": True,
                "city": city_name,
                "latitude": location['lat'],
                "longitude": location['lng'],
                "formatted_address": result['formatted_address'],
                "country": components.get('country', 'Unknown'),
                "country_code": components.get('country', ''),
                "state": components.get('administrative_area_level_1', ''),
                "place_id": result['place_id'],
                "location_type": result['geometry']['location_type'],
                "source": "Google Maps Geocoding API",
                "bounds": result['geometry'].get('bounds', {}),
                "viewport": result['geometry'].get('viewport', {})
            }
            
            log('INFO', f'Google Maps: Found coordinates for {city_name}', {
                'lat': coord_data['latitude'],
                'lng': coord_data['longitude']
            })
            
            return coord_data
        else:
            log('INFO', f'Google Maps: Status {data["status"]} for {city_name}')
            return {
                "success": False,
                "city": city_name,
                "error": f"Google API status: {data['status']}",
                "source": "Google Maps Geocoding API"
            }
            
    except requests.exceptions.RequestException as e:
        log('ERROR', f'Google Maps API request error: {str(e)}')
        return None
    except Exception as e:
        log('ERROR', f'Google Maps processing error: {str(e)}')
        return None

def geocode_nominatim(city_name: str) -> Optional[Dict]:
    """
    Get coordinates using Nominatim (OpenStreetMap) - FREE
    Rate limit: 1 request per second
    Docs: https://nominatim.org/release-docs/latest/api/Search/
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': city_name,
            'format': 'json',
            'limit': 1,
            'addressdetails': 1
        }
        headers = {
            'User-Agent': 'BedrockCityCoordinatesAgent/1.0 (AWS Lambda)'
        }
        
        log('DEBUG', f'Calling Nominatim API for: {city_name}')
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data:
            result = data[0]
            address = result.get('address', {})
            
            coord_data = {
                "success": True,
                "city": city_name,
                "latitude": float(result['lat']),
                "longitude": float(result['lon']),
                "formatted_address": result['display_name'],
                "country": address.get('country', 'Unknown'),
                "country_code": address.get('country_code', '').upper(),
                "state": address.get('state', ''),
                "importance": result.get('importance', 0),
                "source": "Nominatim (OpenStreetMap)",
                "osm_type": result.get('osm_type', ''),
                "osm_id": result.get('osm_id', ''),
                "place_rank": result.get('place_rank', 0)
            }
            
            log('INFO', f'Nominatim: Found coordinates for {city_name}', {
                'lat': coord_data['latitude'],
                'lng': coord_data['longitude']
            })
            
            return coord_data
        else:
            log('INFO', f'Nominatim: No results found for {city_name}')
            return {
                "success": False,
                "city": city_name,
                "error": "No results found",
                "source": "Nominatim (OpenStreetMap)"
            }
            
    except requests.exceptions.RequestException as e:
        log('ERROR', f'Nominatim API request error: {str(e)}')
        return None
    except Exception as e:
        log('ERROR', f'Nominatim processing error: {str(e)}')
        return None

# ==================== FALLBACK LOGIC ====================

def get_coordinates_with_fallback(city_name: str) -> Dict:
    """
    Try multiple providers with fallback logic
    Priority: Preferred Provider -> Other Providers -> Error
    """
    if not city_name or not city_name.strip():
        return {
            "success": False,
            "city": city_name,
            "error": "City name cannot be empty"
        }
    
    providers = {
        'opencage': get_coordinates_opencage,
        'google': get_coordinates_google,
        'nominatim': get_coordinates_nominatim
    }
    
    log('INFO', f'Geocoding request for: {city_name}', {
        'preferred_provider': GEOCODING_PROVIDER
    })
    
    # Try preferred provider first
    if GEOCODING_PROVIDER in providers:
        log('DEBUG', f'Trying preferred provider: {GEOCODING_PROVIDER}')
        result = providers[GEOCODING_PROVIDER](city_name)
        if result and result.get('success'):
            return result
        log('INFO', f'Preferred provider {GEOCODING_PROVIDER} failed or returned no results')
    
    # Try other providers as fallback
    for name, provider_func in providers.items():
        if name != GEOCODING_PROVIDER:
            log('DEBUG', f'Trying fallback provider: {name}')
            result = provider_func(city_name)
            if result and result.get('success'):
                result['note'] = f'Fallback provider used (primary provider "{GEOCODING_PROVIDER}" failed)'
                return result
    
    # All providers failed
    log('ERROR', f'All geocoding providers failed for: {city_name}')
    return {
        "success": False,
        "city": city_name,
        "error": "Unable to geocode city with any provider. Please check the city name and try again.",
        "attempted_providers": list(providers.keys()),
        "configured_provider": GEOCODING_PROVIDER
    }

# ==================== DISTANCE CALCULATION ====================


def calculate_distance(city1: str, city2: str, 
                      state1: Optional[str] = None, 
                      state2: Optional[str] = None,
                      country1: Optional[str] = None, 
                      country2: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate distance between two cities using the Haversine formula.
    Now includes scaled coordinates for both cities.
    """
    # Get coordinates for both cities
    coords1 = get_coordinates(city1, state1, country1)
    coords2 = get_coordinates(city2, state2, country2)

    if 'error' in coords1:
        return coords1
    if 'error' in coords2:
        return coords2

    # Calculate distance
    lat1, lon1 = coords1['latitude'], coords1['longitude']
    lat2, lon2 = coords2['latitude'], coords2['longitude']

    # Haversine formula
    R = 6371  # Earth's radius in kilometers

    lat1_rad, lon1_rad = radians(lat1), radians(lon1)
    lat2_rad, lon2_rad = radians(lat2), radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    distance_km = R * c
    distance_miles = distance_km * 0.621371

    return {
        'city1': {
            'name': city1,
            'latitude': lat1,
            'longitude': lon1,
            'scaled_latitude': coords1['scaled_latitude'],
            'scaled_longitude': coords1['scaled_longitude'],
            'country': coords1.get('country', ''),
            'formatted_address': coords1.get('formatted_address', '')
        },
        'city2': {
            'name': city2,
            'latitude': lat2,
            'longitude': lon2,
            'scaled_latitude': coords2['scaled_latitude'],
            'scaled_longitude': coords2['scaled_longitude'],
            'country': coords2.get('country', ''),
            'formatted_address': coords2.get('formatted_address', '')
        },
        'distance_km': round(distance_km, 2),
        'distance_miles': round(distance_miles, 2)
    }


def get_nearest_graph_vertices(city: str, state: Optional[str] = None,
                               country: Optional[str] = None,
                               limit: int = 2) -> Dict[str, Any]:
    """Find nearest graph vertices to a city's coordinates."""
    #coords = get_coordinates(city, state, country)
    #if 'error' in coords:
    #    return coords

    try:
        #nearest = find_nearest_vertices(
        #    coords['scaled_latitude'],
        #    coords['scaled_longitude'],
        #    limit
        #)
        nearest = find_nearest_vertices(
            45520247,  #coords['scaled_latitude'],
            -122674194, #coords['scaled_longitude'],
            2 #limit
        )
        print(nearest)

        return {
        #    'query_location': {
        #        'city': city,
        #        'state': state,
        #        'country': country,
        #        'latitude': coords['latitude'],
        #        'longitude': coords['longitude'],
        #        'scaled_latitude': coords['scaled_latitude'],
        #        'scaled_longitude': coords['scaled_longitude'],
        #        'formatted_address': coords.get('formatted_address', '')
        #    },
            'nearest_vertices': nearest,
            'count': len(nearest)
        }

    except Exception as e:
        logger.error(f"Error finding nearest vertices: {str(e)}", exc_info=True)
        return {
            'error': f"Failed to query graph database: {str(e)}",
            'query_location': {
                'city': city,
                'latitude': coords.get('latitude'),
                'longitude': coords.get('longitude')
            }
        }


def get_graph_vertex(vertex_id: str) -> Dict[str, Any]:
    """Retrieve a specific vertex from the graph by ID."""
    try:
        vertex = get_vertex_by_id(vertex_id)

        if vertex is None:
            return {
                'error': f'Vertex not found: {vertex_id}'
            }

        return vertex

    except Exception as e:
        logger.error(f"Error retrieving vertex: {str(e)}", exc_info=True)
        return {
            'error': f"Failed to retrieve vertex: {str(e)}"
        }


def find_graph_path(start_vertex_id: str, end_vertex_id: str, 
                   max_hops: int = 5) -> Dict[str, Any]:
    """Find shortest path between two vertices in the graph."""
    try:
        path = find_path_between_vertices(start_vertex_id, end_vertex_id, max_hops)

        if path is None:
            return {
                'error': f'No path found between {start_vertex_id} and {end_vertex_id}',
                'start_vertex_id': start_vertex_id,
                'end_vertex_id': end_vertex_id,
                'max_hops': max_hops
            }

        return path

    except Exception as e:
        logger.error(f"Error finding path: {str(e)}", exc_info=True)
        return {
            'error': f"Failed to find path: {str(e)}"
        }


def get_neighbors(vertex_id: str, relationship_type: Optional[str] = None,
                 direction: str = 'both', limit: int = 10) -> Dict[str, Any]:
    """Get neighboring vertices connected to a given vertex."""
    try:
        neighbors = get_vertex_neighbors(vertex_id, relationship_type, direction, limit)

        return {
            'vertex_id': vertex_id,
            'relationship_type': relationship_type,
            'direction': direction,
            'neighbors': neighbors,
            'count': len(neighbors)
        }

    except Exception as e:
        logger.error(f"Error getting neighbors: {str(e)}", exc_info=True)
        return {
            'error': f"Failed to get neighbors: {str(e)}"
        }

        
def test_neptune_connection() -> Dict[str, Any]:
    """Test Neptune database connection and return stats."""
    try:
        return test_connection()
    except Exception as e:
        logger.error(f"Neptune connection test failed: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e)
        }


# ==================== LAMBDA HANDLER ====================


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for Bedrock Agent action group."""
    logger.info(f"Received event: {json.dumps(event, default=str)}")

    action_group = event.get('actionGroup', '')
    api_path = event.get('apiPath', '')
    http_method = event.get('httpMethod', '')
    parameters = event.get('parameters', [])

    params = {p['name']: p['value'] for p in parameters}

    logger.info(f"Action: {api_path}, Method: {http_method}, Params: {params}")

    try:
        # Route to appropriate handler
        if api_path == '/coordinates':
            result = get_coordinates(
                params.get('city', ''),
                params.get('state'),
                params.get('country')
            )
        elif api_path == '/distance':
            result = calculate_distance(
                params.get('city1', ''),
                params.get('city2', ''),
                params.get('state1'),
                params.get('state2'),
                params.get('country1'),
                params.get('country2')
            )
        elif api_path == '/nearest-vertices':
            result = get_nearest_graph_vertices(
                params.get('city', ''),
                params.get('state'),
                params.get('country'),
                int(params.get('limit', 2))
            )
        elif api_path == '/vertex':
            result = get_graph_vertex(params.get('vertex_id', ''))
        elif api_path == '/path':
            result = find_graph_path(
                params.get('start_vertex_id', ''),
                params.get('end_vertex_id', ''),
                int(params.get('max_hops', 5))
            )
        elif api_path == '/neighbors':
            result = get_neighbors(
                params.get('vertex_id', ''),
                params.get('relationship_type'),
                params.get('direction', 'both'),
                int(params.get('limit', 10))
            )
        elif api_path == '/test-connection':
            result = test_neptune_connection()
        else:
            result = {'error': f'Unknown API path: {api_path}'}

        response_code = 200 if 'error' not in result else 400

    except Exception as e:
        logger.error(f"Handler error: {str(e)}", exc_info=True)
        result = {'error': str(e)}
        response_code = 500

    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': http_method,
            'httpStatusCode': response_code,
            'responseBody': {
                'application/json': {
                    'body': json.dumps(result)
                }
            }
        }
    }
# ==================== LOCAL TESTING ====================

if __name__ == "__main__":
    """Local testing"""
    
    # Test event for single city
    test_event_single = {
      "actionGroup": "CityCoordinatesActions",
      "apiPath": "/nearest-vertices",
      "httpMethod": "get",
      "parameters": [
        {
          "name": "city",
          "value": "portland"
        },
        {
          "name": "state",
          "value": "oregon"
        },
        {
          "name": "country",
          "value": "usa"
        },
        {
          "name": "limit",
          "value": 3
        }
      ]
    }

    # Test event for two cities
    test_event_two = {
        "messageVersion": "1.0",
        "agent": {
            "name": "city-coordinates-agent",
            "version": "DRAFT",
            "id": "TEST123",
            "alias": "TSTALIASID"
        },
        "actionGroup": "CityCoordinatesActions",
        "apiPath": "/getTwoCitiesCoordinates",
        "httpMethod": "GET",
        "parameters": [
            {
                "name": "sourceCity",
                "type": "string",
                "value": "London"
            },
            {
                "name": "destinationCity",
                "type": "string",
                "value": "New York"
            }
        ]
    }
    
    # Mock context
    class MockContext:
        request_id = "test-request-123"
        function_name = "test-function"
        memory_limit_in_mb = 256
        invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"

    def run_test_suite(agent_id: str, alias_id: str, region: str):
        """Run comprehensive test suite"""
        tests = [
            # ... existing tests ...
            
            {
                'name': 'Scaled Coordinates Verification',
                'prompt': 'What are the coordinates for Portland, Oregon? Please show both decimal and scaled integer formats.',
                'expectations': [
                    'latitude',
                    'longitude',
                    'scaled',
                    '45515200',  # Expected scaled latitude
                    '122678400'  # Expected scaled longitude (absolute value)
                ]
            },
        ]
    
    # ... rest of test suite ...
# have to redo all the tests, API change
 #   print("\n" + "="*80)
 #   print("Testing Single City Lookup")
 #   print("="*80)
    result1 = lambda_handler(test_event_single, MockContext())
 #   print(json.dumps(result1, indent=2, cls=DecimalEncoder))
 #   
 #   print("\n" + "="*80)
 #   print("Testing Two Cities Lookup with Distance")
 #   print("="*80)
 #   result2 = lambda_handler(test_event_two, MockContext())
 #   print(json.dumps(result2, indent=2, cls=DecimalEncoder))