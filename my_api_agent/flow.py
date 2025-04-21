from pocketflow import Flow
# Import all the node classes we defined
from .nodes import (
    LoadAllSpecs,
    DecomposeQuery,
    SelectSpec,
    FindAndPrepareApi,
    ExecuteAPI,
    SummarizeResults
)

def create_api_agent_flow() -> Flow:
    """Creates and connects the nodes for the API agent flow."""
    
    # 1. Instantiate the nodes
    load_all_specs = LoadAllSpecs()
    decompose_query = DecomposeQuery()
    select_spec = SelectSpec()
    find_and_prepare_api = FindAndPrepareApi()
    execute_api = ExecuteAPI()
    summarize_results = SummarizeResults()
    
    # 2. Define the transitions based on the design document
    
    # Start -> Load Specs -> Decompose Query
    load_all_specs >> decompose_query
    
    # Decompose Query -> Start Task Loop (Select Spec)
    decompose_query - "process_task" >> select_spec
    
    # Task Loop (Select Spec Node)
    # If spec is selected successfully, proceed to find/prepare API
    select_spec - "spec_selected" >> find_and_prepare_api
    # If no more tasks are pending, go to summarization
    select_spec - "summarize" >> summarize_results
    # If spec selection failed for the current task, loop back to try the next task
    select_spec - "process_task_loop" >> select_spec
    
    # Find and Prepare API Node
    # If API details are prepared successfully, proceed to execution
    find_and_prepare_api - "execute" >> execute_api
    # If API finding/preparation failed, loop back to try the next task
    find_and_prepare_api - "process_task_loop" >> select_spec
    
    # Execute API Node
    # After execution (success or failure), always loop back to SelectSpec to process the next task
    execute_api - "process_task_loop" >> select_spec
    
    # Summarize Node is the end - post() returns None, so no outgoing transitions needed.
    
    # 3. Create the Flow instance, starting with the first node
    api_agent_flow = Flow(start=load_all_specs)
    
    print("API Agent Flow created successfully.")
    return api_agent_flow

# Example of how to use it (will be used in main.py)
if __name__ == '__main__':
    # This part is just for demonstration, actual execution happens in main.py
    flow = create_api_agent_flow()
    # You would typically run it like this:
    # shared_data = { ... initial data ... }
    # flow.run(shared_data)
    print(f"Flow starts with node: {flow.start_node.__class__.__name__}")
    # You could potentially inspect transitions here if needed for debugging
    # print(flow.transitions)
