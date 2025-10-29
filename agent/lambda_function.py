# lambda_function.py
import json
import os
import requests
from typing import Dict, Any, Optional
from decimal import Decimal
from math import radians, sin, cos, sqrt, atan2

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

# ==================== GEOCODING PROVIDERS ====================

def get_coordinates_opencage(city_name: str) -> Optional[Dict]:
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

def get_coordinates_google(city_name: str) -> Optional[Dict]:
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

def get_coordinates_nominatim(city_name: str) -> Optional[Dict]:
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

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Dict:
    """
    Calculate distance between two coordinates using Haversine formula
    Returns distance in kilometers and miles
    """
    try:
        # Earth radius in kilometers
        R = 6371.0
        
        # Convert to radians
        lat1_rad = radians(lat1)
        lon1_rad = radians(lon1)
        lat2_rad = radians(lat2)
        lon2_rad = radians(lon2)
        
        # Haversine formula
        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad
        a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance_km = R * c
        distance_miles = distance_km * 0.621371
        
        # Calculate bearing (direction)
        y = sin(dlon) * cos(lat2_rad)
        x = cos(lat1_rad) * sin(lat2_rad) - sin(lat1_rad) * cos(lat2_rad) * cos(dlon)
        bearing = atan2(y, x)
        bearing_degrees = (bearing * 180 / 3.14159) % 360
        
        # Determine cardinal direction
        directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        direction_index = round(bearing_degrees / 45) % 8
        cardinal_direction = directions[direction_index]
        
        result = {
            "distance_km": round(distance_km, 2),
            "distance_miles": round(distance_miles, 2),
            "straight_line": True,
            "bearing_degrees": round(bearing_degrees, 2),
            "direction": cardinal_direction,
            "note": "This is the straight-line (as the crow flies) distance, not driving distance"
        }
        
        log('INFO', 'Distance calculated', result)
        return result
        
    except Exception as e:
        log('ERROR', f'Distance calculation error: {str(e)}')
        return {
            "error": f"Failed to calculate distance: {str(e)}"
        }

# ==================== API HANDLERS ====================

def get_single_city_coordinates(city_name: str) -> Dict:
    """Get coordinates for a single city"""
    log('INFO', f'Single city request: {city_name}')
    return get_coordinates_with_fallback(city_name)

def get_two_cities_coordinates(source_city: str, destination_city: str) -> Dict:
    """Get coordinates for two cities and calculate distance"""
    log('INFO', f'Two cities request: {source_city} -> {destination_city}')
    
    # Get coordinates for both cities
    source_coords = get_coordinates_with_fallback(source_city)
    dest_coords = get_coordinates_with_fallback(destination_city)
    
    result = {
        "source": source_coords,
        "destination": dest_coords
    }
    
    # Calculate distance if both lookups succeeded
    if source_coords.get('success') and dest_coords.get('success'):
        try:
            distance = calculate_distance(
                source_coords['latitude'],
                source_coords['longitude'],
                dest_coords['latitude'],
                dest_coords['longitude']
            )
            result["distance"] = distance
            
            # Add travel context
            result["travel_context"] = {
                "from": f"{source_coords.get('formatted_address', source_city)}",
                "to": f"{dest_coords.get('formatted_address', destination_city)}",
                "summary": f"From {source_coords.get('country', 'Unknown')} to {dest_coords.get('country', 'Unknown')}"
            }
        except Exception as e:
            log('ERROR', f'Error calculating distance: {str(e)}')
            result["distance_error"] = str(e)
    else:
        result["note"] = "Distance not calculated because one or both cities could not be geocoded"
    
    return result

# ==================== LAMBDA HANDLER ====================

def lambda_handler(event, context):
    """
    AWS Lambda handler for Bedrock Agent Action Group
    
    Expected event structure from Bedrock Agent:
    {
        "messageVersion": "1.0",
        "agent": {...},
        "actionGroup": "CityCoordinatesActions",
        "apiPath": "/getCityCoordinates" or "/getTwoCitiesCoordinates",
        "httpMethod": "GET",
        "parameters": [
            {"name": "cityName", "type": "string", "value": "Tokyo"},
            ...
        ]
    }
    """
    log('INFO', 'Lambda invoked', {
        'requestId': context.request_id if context else 'local',
        'apiPath': event.get('apiPath', 'unknown')
    })
    
    try:
        # Extract event details
        action_group = event.get('actionGroup', '')
        api_path = event.get('apiPath', '')
        http_method = event.get('httpMethod', 'GET')
        parameters = event.get('parameters', [])
        
        # Convert parameters list to dict
        params_dict = {}
        for param in parameters:
            param_name = param.get('name', '')
            param_value = param.get('value', '')
            if param_name:
                params_dict[param_name] = param_value
        
        log('DEBUG', 'Request parameters', {
            'api_path': api_path,
            'params': params_dict
        })
        
        # Route to appropriate handler
        response_body = {}
        
        if api_path == '/getCityCoordinates':
            city_name = params_dict.get('cityName', '')
            if not city_name:
                response_body = {
                    "success": False,
                    "error": "cityName parameter is required"
                }
            else:
                response_body = get_single_city_coordinates(city_name)
        
        elif api_path == '/getTwoCitiesCoordinates':
            source_city = params_dict.get('sourceCity', '')
            destination_city = params_dict.get('destinationCity', '')
            
            if not source_city or not destination_city:
                response_body = {
                    "success": False,
                    "error": "Both sourceCity and destinationCity parameters are required"
                }
            else:
                response_body = get_two_cities_coordinates(source_city, destination_city)
        
        else:
            response_body = {
                "success": False,
                "error": f"Unknown API path: {api_path}",
                "supported_paths": ["/getCityCoordinates", "/getTwoCitiesCoordinates"]
            }
        
        # Format response for Bedrock Agent
        response = {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': action_group,
                'apiPath': api_path,
                'httpMethod': http_method,
                'httpStatusCode': 200,
                'responseBody': {
                    'application/json': {
                        'body': json.dumps(response_body, cls=DecimalEncoder)
                    }
                }
            }
        }
        
        log('INFO', 'Request completed successfully', {
            'api_path': api_path,
            'success': response_body.get('success', False)
        })
        
        return response
    
    except Exception as e:
        log('ERROR', f'Unhandled error in lambda_handler: {str(e)}', {
            'error_type': type(e).__name__,
            'event': event
        })
        
        # Return error response
        error_response = {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup', ''),
                'apiPath': event.get('apiPath', ''),
                'httpMethod': event.get('httpMethod', 'GET'),
                'httpStatusCode': 500,
                'responseBody': {
                    'application/json': {
                        'body': json.dumps({
                            "success": False,
                            "error": f"Internal error: {str(e)}",
                            "error_type": type(e).__name__
                        })
                    }
                }
            }
        }
        
        return error_response

# ==================== LOCAL TESTING ====================

if __name__ == "__main__":
    """Local testing"""
    
    # Test event for single city
    test_event_single = {
        "messageVersion": "1.0",
        "agent": {
            "name": "city-coordinates-agent",
            "version": "DRAFT",
            "id": "TEST123",
            "alias": "TSTALIASID"
        },
        "actionGroup": "CityCoordinatesActions",
        "apiPath": "/getCityCoordinates",
        "httpMethod": "GET",
        "parameters": [
            {
                "name": "cityName",
                "type": "string",
                "value": "Tokyo"
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
    
    print("\n" + "="*80)
    print("Testing Single City Lookup")
    print("="*80)
    result1 = lambda_handler(test_event_single, MockContext())
    print(json.dumps(result1, indent=2, cls=DecimalEncoder))
    
    print("\n" + "="*80)
    print("Testing Two Cities Lookup with Distance")
    print("="*80)
    result2 = lambda_handler(test_event_two, MockContext())
    print(json.dumps(result2, indent=2, cls=DecimalEncoder))