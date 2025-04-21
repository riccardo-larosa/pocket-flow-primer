import requests
import json
from typing import Dict, Any

def execute_api_call(api_details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes an API call based on the provided details.

    Args:
        api_details: A dictionary containing necessary information like:
            'method': HTTP method (GET, POST, PUT, DELETE, etc.)
            'url': The full URL for the endpoint.
            'headers': Optional dictionary of request headers.
            'params': Optional dictionary of query parameters (for GET).
            'body': Optional dictionary or string for the request body (for POST, PUT).

    Returns:
        A dictionary containing:
            'status_code': The HTTP status code of the response.
            'body': The response body (parsed as JSON if possible, otherwise text).
            'error': An error message string if the request failed, otherwise None.
    """
    method = api_details.get('method', 'GET').upper()
    url = api_details.get('url')
    headers = api_details.get('headers', {})
    params = api_details.get('params', None)
    body_data = api_details.get('body', None)

    if not url:
        return {"status_code": None, "body": None, "error": "API URL is missing"}

    # Ensure Content-Type is set for JSON body if not provided
    if isinstance(body_data, dict) and 'Content-Type' not in headers:
        headers['Content-Type'] = 'application/json'

    # Convert dict body to JSON string if needed
    json_body = None
    if isinstance(body_data, dict):
        try:
            json_body = json.dumps(body_data)
        except Exception as e:
             return {"status_code": None, "body": None, "error": f"Failed to serialize JSON body: {e}"}
    elif isinstance(body_data, str):
        json_body = body_data # Assume it's pre-formatted JSON or other string body

    print(f"Executing API call: {method} {url}")
    print(f"  Headers: {headers}")
    print(f"  Params: {params}")
    print(f"  Body: {json_body}")

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            data=json_body, # requests handles data appropriately
            timeout=30 # Add a timeout
        )
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        try:
            response_body = response.json()
        except json.JSONDecodeError:
            response_body = response.text

        print(f"API Response: {response.status_code}")
        return {
            "status_code": response.status_code,
            "body": response_body,
            "error": None
        }

    except requests.exceptions.RequestException as e:
        print(f"API Request failed: {e}")
        status_code = e.response.status_code if e.response is not None else None
        error_body = e.response.text if e.response is not None else str(e)
        return {
            "status_code": status_code,
            "body": error_body,
            "error": f"Request failed: {e}"
        }
    except Exception as e:
        # Catch any other unexpected errors during the request
        print(f"Unexpected error during API execution: {e}")
        return {"status_code": None, "body": None, "error": f"Unexpected error: {e}"}


# Example usage (for testing)
if __name__ == "__main__":
    print("--- Testing GET request ---")
    get_details = {
        'method': 'GET',
        'url': 'https://httpbin.org/get',
        'params': {'show_env': '1'}
    }
    get_result = execute_api_call(get_details)
    print("GET Result:", json.dumps(get_result, indent=2))
    assert get_result["status_code"] == 200
    assert get_result["error"] is None
    assert 'args' in get_result["body"]
    assert get_result["body"]['args']['show_env'] == '1'

    print("\n--- Testing POST request ---")
    post_details = {
        'method': 'POST',
        'url': 'https://httpbin.org/post',
        'body': {'name': 'PocketFlow', 'value': 42}
    }
    post_result = execute_api_call(post_details)
    print("POST Result:", json.dumps(post_result, indent=2))
    assert post_result["status_code"] == 200
    assert post_result["error"] is None
    assert post_result["body"]["json"] == {'name': 'PocketFlow', 'value': 42}

    print("\n--- Testing Error case (404) ---")
    error_details = {
        'method': 'GET',
        'url': 'https://httpbin.org/status/404'
    }
    error_result = execute_api_call(error_details)
    print("Error Result:", json.dumps(error_result, indent=2))
    assert error_result["status_code"] == 404
    assert error_result["error"] is not None

    print("\n--- Testing Missing URL ---")
    missing_url_details = {'method': 'GET'}
    missing_url_result = execute_api_call(missing_url_details)
    print("Missing URL Result:", json.dumps(missing_url_result, indent=2))
    assert missing_url_result["error"] == "API URL is missing"
