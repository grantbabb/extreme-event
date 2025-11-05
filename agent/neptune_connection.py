# neptune_connection.py

import os
import logging
import requests
from typing import Dict, Any, List, Optional
# import json
from requests_aws4auth import AWS4Auth
import boto3

logger = logging.getLogger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

# Neptune configuration from environment
NEPTUNE_ENDPOINT = os.getenv('NEPTUNE_ENDPOINT', '')
NEPTUNE_PORT = int(os.getenv('NEPTUNE_PORT', '8182'))
NEPTUNE_USE_IAM = os.getenv('NEPTUNE_USE_IAM', 'true').lower() == 'true'


class NeptuneConnection:
    """Manages connection to Neptune database using OpenCypher"""

    def __init__(self):
        self._session = None
        self._auth = None
        self._base_url = None

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()

    def connect(self):
        """Establish connection to Neptune"""
        if self._session:
            return  # Already connected

        if not NEPTUNE_ENDPOINT:
            raise ValueError("NEPTUNE_ENDPOINT environment variable not set")

        try:
            # Create base URL for OpenCypher endpoint
            protocol = 'https' if NEPTUNE_USE_IAM else 'http'
            self._base_url = f"{protocol}://{NEPTUNE_ENDPOINT}:{NEPTUNE_PORT}/openCypher"

            logger.info(f"Connecting to Neptune OpenCypher at {self._base_url}")

            # Create session
            self._session = requests.Session()

            # Setup IAM authentication if needed
            if NEPTUNE_USE_IAM:
                credentials = boto3.Session().get_credentials()
                region = os.getenv('AWS_REGION', 'us-west-2')
                self._auth = AWS4Auth(
                    credentials.access_key,
                    credentials.secret_key,
                    region,
                    'neptune-db',
                    session_token=credentials.token
                )

            # Test connection with a simple query
            test_result = self.execute_query("MATCH (n) RETURN count(n) as count LIMIT 1")
            logger.info(f"Successfully connected to Neptune. Test query result: {test_result}")

        except Exception as e:
            logger.error(f"Failed to connect to Neptune: {str(e)}", exc_info=True)
            raise ConnectionError(f"Neptune connection failed: {str(e)}")

    def close(self):
        """Close Neptune connection"""
        if self._session:
            try:
                self._session.close()
                logger.info("Neptune connection closed")
            except Exception as e:
                logger.error(f"Error closing Neptune connection: {str(e)}")
            finally:
                self._session = None
                self._auth = None

    def execute_query(self, query: str, parameters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Execute an OpenCypher query

        Args:
            query: OpenCypher query string
            parameters: Optional parameter dictionary

        Returns:
            Query results as list of dictionaries
        """
        if not self._session:
            self.connect()

        try:
            logger.info(f"Executing query: {query}")
            if parameters:
                logger.info(f"With parameters: {parameters}")

            # Prepare request payload
            payload = {'query': query}
            if parameters:
                payload['parameters'] = parameters

            # Execute query
            headers = {'Content-Type': 'application/json'}

            if NEPTUNE_USE_IAM:
                response = self._session.post(
                    self._base_url,
                    json=payload,
                    headers=headers,
                    auth=self._auth,
                    timeout=30
                )
            else:
                response = self._session.post(
                    self._base_url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )

            # Check for errors
            response.raise_for_status()

            # Parse results
            result_data = response.json()

            # Extract results from response
            if 'results' in result_data:
                results = result_data['results']
            else:
                results = result_data

            logger.info(f"Query returned {len(results) if isinstance(results, list) else 1} results")
            return results if isinstance(results, list) else [results]

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request error: {str(e)}", exc_info=True)
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Query execution error: {str(e)}", exc_info=True)
            raise

def find_nearest_vertices(scaled_lat: int, scaled_lon: int, limit: int = 2) -> List[Dict[str, Any]]:
    """
    Find vertices nearest to given scaled coordinates using OpenCypher

    Args:
        scaled_lat: Latitude scaled by 10^6
        scaled_lon: Longitude scaled by 10^6
        limit: Number of nearest vertices to return (default 2)

    Returns:
        List of nearest vertices with their properties and distances
    """
    with NeptuneConnection() as conn:
        # OpenCypher query to find nearest vertices
        # Using Manhattan distance for performance
        query = """
        MATCH (n)
        WHERE n.scaled_latitude IS NOT NULL 
          AND n.scaled_longitude IS NOT NULL
        WITH n,
             abs(n.scaled_latitude - $target_lat) + abs(n.scaled_longitude - $target_lon) AS distance
        ORDER BY distance ASC
        LIMIT $limit
        RETURN 
            id(n) AS vertex_id,
            labels(n) AS vertex_labels,
            n.scaled_latitude AS scaled_latitude,
            n.scaled_longitude AS scaled_longitude,
            distance,
            properties(n) AS properties
        """

        parameters = {
            'target_lat': scaled_lat,
            'target_lon': scaled_lon,
            'limit': limit
        }

        try:
            results = conn.execute_query(query, parameters)

            # Format results
            formatted_results = []
            for result in results:
                vertex = {
                    'vertex_id': result.get('vertex_id'),
                    'vertex_labels': result.get('vertex_labels', []),
                    'vertex_label': result.get('vertex_labels', [''])[0] if result.get('vertex_labels') else '',
                    'scaled_latitude': result.get('scaled_latitude'),
                    'scaled_longitude': result.get('scaled_longitude'),
                    'manhattan_distance': result.get('distance'),
                    'properties': result.get('properties', {})
                }

                # Convert scaled coordinates back to decimal for display
                if vertex['scaled_latitude'] is not None and vertex['scaled_longitude'] is not None:
                    vertex['latitude'] = vertex['scaled_latitude'] / 1_000_000
                    vertex['longitude'] = vertex['scaled_longitude'] / 1_000_000

                formatted_results.append(vertex)

            logger.info(f"Found {len(formatted_results)} nearest vertices")
            return formatted_results

        except Exception as e:
            logger.error(f"Error finding nearest vertices: {str(e)}", exc_info=True)
            raise


def get_vertex_by_id(vertex_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a vertex by its ID using OpenCypher

    Args:
        vertex_id: The vertex identifier

    Returns:
        Vertex properties or None if not found
    """
    with NeptuneConnection() as conn:
        query = """
        MATCH (n)
        WHERE id(n) = $vertex_id
        RETURN 
            id(n) AS vertex_id,
            labels(n) AS vertex_labels,
            properties(n) AS properties
        """

        parameters = {'vertex_id': vertex_id}

        try:
            results = conn.execute_query(query, parameters)

            if not results:
                return None

            result = results[0]
            return {
                'vertex_id': result.get('vertex_id'),
                'vertex_labels': result.get('vertex_labels', []),
                'vertex_label': result.get('vertex_labels', [''])[0] if result.get('vertex_labels') else '',
                'properties': result.get('properties', {})
            }

        except Exception as e:
            logger.error(f"Error retrieving vertex: {str(e)}", exc_info=True)
            return None

def find_path_between_vertices(start_id: str, end_id: str, max_hops: int = 5) -> Optional[Dict[str, Any]]:
    """
    Find shortest path between two vertices

    Args:
        start_id: Starting vertex ID
        end_id: Ending vertex ID
        max_hops: Maximum number of hops to search (default 5)

    Returns:
        Path information or None if no path found
    """
    with NeptuneConnection() as conn:
        query = """
        MATCH path = shortestPath((start)-[*..%d]-(end))
        WHERE id(start) = $start_id AND id(end) = $end_id
        RETURN 
            [node IN nodes(path) | {id: id(node), labels: labels(node), properties: properties(node)}] AS nodes,
            [rel IN relationships(path) | {id: id(rel), type: type(rel), properties: properties(rel)}] AS relationships,
            length(path) AS path_length
        LIMIT 1
        """ % max_hops

        parameters = {
            'start_id': start_id,
            'end_id': end_id
        }

        try:
            results = conn.execute_query(query, parameters)

            if not results:
                return None

            result = results[0]
            return {
                'nodes': result.get('nodes', []),
                'relationships': result.get('relationships', []),
                'path_length': result.get('path_length', 0),
                'start_id': start_id,
                'end_id': end_id
            }

        except Exception as e:
            logger.error(f"Error finding path: {str(e)}", exc_info=True)
            return None

def get_vertex_neighbors(vertex_id: str, relationship_type: Optional[str] = None, 
                        direction: str = 'both', limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get neighboring vertices connected to a given vertex

    Args:
        vertex_id: The vertex identifier
        relationship_type: Optional relationship type to filter by
        direction: 'outgoing', 'incoming', or 'both' (default 'both')
        limit: Maximum number of neighbors to return

    Returns:
        List of neighboring vertices with relationship information
    """
    with NeptuneConnection() as conn:
        # Build relationship pattern based on direction
        if direction == 'outgoing':
            rel_pattern = '-[r]->'
        elif direction == 'incoming':
            rel_pattern = '<-[r]-'
        else:
            rel_pattern = '-[r]-'

        # Add relationship type filter if specified
        if relationship_type:
            rel_pattern = rel_pattern.replace('[r]', f'[r:{relationship_type}]')

        query = f"""
        MATCH (start){rel_pattern}(neighbor)
        WHERE id(start) = $vertex_id
        RETURN 
            id(neighbor) AS neighbor_id,
            labels(neighbor) AS neighbor_labels,
            properties(neighbor) AS neighbor_properties,
            type(r) AS relationship_type,
            properties(r) AS relationship_properties
        LIMIT $limit
        """

        parameters = {
            'vertex_id': vertex_id,
            'limit': limit
        }

        try:
            results = conn.execute_query(query, parameters)

            formatted_results = []
            for result in results:
                neighbor = {
                    'vertex_id': result.get('neighbor_id'),
                    'vertex_labels': result.get('neighbor_labels', []),
                    'vertex_label': result.get('neighbor_labels', [''])[0] if result.get('neighbor_labels') else '',
                    'properties': result.get('neighbor_properties', {}),
                    'relationship_type': result.get('relationship_type'),
                    'relationship_properties': result.get('relationship_properties', {})
                }
                formatted_results.append(neighbor)

            logger.info(f"Found {len(formatted_results)} neighbors")
            return formatted_results

        except Exception as e:
            logger.error(f"Error getting neighbors: {str(e)}", exc_info=True)
            raise


def test_connection() -> Dict[str, Any]:
    """
    Test Neptune connection and return basic stats
    
    Returns:
        Dictionary with connection status and stats
    """
    try:
        with NeptuneConnection() as conn:
            # Get vertex count
            vertex_count_query = "MATCH (n) RETURN count(n) AS count"
            vertex_count_result = conn.execute_query(vertex_count_query)
            vertex_count = vertex_count_result[0].get('count', 0) if vertex_count_result else 0

            # Get edge count
            edge_count_query = "MATCH ()-[r]->() RETURN count(r) AS count"
            edge_count_result = conn.execute_query(edge_count_query)
            edge_count = edge_count_result[0].get('count', 0) if edge_count_result else 0

            # Get vertex labels
            labels_query = "MATCH (n) RETURN DISTINCT labels(n) AS labels LIMIT 10"
            labels_result = conn.execute_query(labels_query)
            labels = [r.get('labels', []) for r in labels_result]
            # Flatten and deduplicate labels
            all_labels = list(set([label for sublist in labels for label in sublist]))

            # Get relationship types
            rel_types_query = "MATCH ()-[r]->() RETURN DISTINCT type(r) AS type LIMIT 10"
            rel_types_result = conn.execute_query(rel_types_query)
            rel_types = [r.get('type') for r in rel_types_result if r.get('type')]

            return {
                'status': 'connected',
                'endpoint': NEPTUNE_ENDPOINT,
                'port': NEPTUNE_PORT,
                'query_language': 'OpenCypher',
                'iam_auth': NEPTUNE_USE_IAM,
                'vertex_count': vertex_count,
                'edge_count': edge_count,
                'vertex_labels': all_labels,
                'relationship_types': rel_types
            }

    except Exception as e:
        logger.error(f"Connection test failed: {str(e)}", exc_info=True)
        return {
            'status': 'failed',
            'error': str(e),
            'endpoint': NEPTUNE_ENDPOINT
        }
        