import sys
import os
import pprint # For pretty printing results

# Ensure the project root is in the Python path for imports
# This allows running 'python main.py' from the 'my_api_agent' directory
project_root = os.path.dirname(os.path.abspath(__file__))
# sys.path.insert(0, project_root) # Usually not needed if running as module

# Import the flow creation function
from flow import create_api_agent_flow

def main():
    """Sets up the initial state, runs the flow, and prints the result."""
    
    # --- Configuration ---
    # TODO: Replace with your actual user query
    user_query = "Find the product details for SKU 'ABC-123' and then create a new order for 5 units of it."
    
    # TODO: Replace with the path to your OpenAPI spec directory or list of files
    # Using the dummy directory created by the openapi_parser test for this example
    # You might need to run 'python utils/openapi_parser.py' once first to create it,
    # or point this to your actual spec location.
    spec_source = "temp_specs" 
    if not os.path.isdir(spec_source):
        print(f"Error: OpenAPI specification source directory '{spec_source}' not found.")
        print("Please ensure the directory exists or run 'python utils/openapi_parser.py' to create dummy specs.")
        sys.exit(1)
        
    # --- Initial Shared State ---
    # Based on the design document
    initial_shared_state = {
        "user_query": user_query,
        "openapi_spec_source": spec_source,
        "loaded_specs": None,        # Will be populated by LoadAllSpecs
        "sub_tasks": [],             # Will be populated by DecomposeQuery
        "task_results": {},          # Will be populated by ExecuteAPI
        "current_task_id": None,     # Managed by SelectSpec
        "final_summary": None        # Will be populated by SummarizeResults
    }
    
    print("--- Initializing API Agent Flow ---")
    print(f"User Query: {initial_shared_state['user_query']}")
    print(f"Spec Source: {initial_shared_state['openapi_spec_source']}")
    
    # Create the flow instance
    api_agent_flow = create_api_agent_flow()
    
    print("\n--- Running API Agent Flow ---")
    try:
        # Execute the flow with the initial state
        api_agent_flow.run(initial_shared_state)
        print("\n--- Flow Execution Completed ---")
        
    except Exception as e:
        print(f"\n--- Flow Execution Failed --- ")
        print(f"Error: {e}")
        # Optionally print the state at failure for debugging
        print("\n--- Final State (at failure) ---")
        pprint.pprint(initial_shared_state)
        sys.exit(1)
        
    # Print the final results
    print("\n--- Final State (successful run) ---")
    # Pretty print the whole state for inspection
    pprint.pprint(initial_shared_state) 
    
    print("\n=======================================")
    print(" Final Summary from Agent:")
    print("=======================================")
    final_summary = initial_shared_state.get("final_summary", "No summary was generated.")
    print(final_summary)
    print("=======================================")

if __name__ == "__main__":
    main()
