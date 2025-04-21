from pocketflow import Node
# Import the utility function we just created
from utils.openapi_parser import load_all_specs_from_source
from utils.call_llm import call_llm
import re # For parsing the LLM output
import yaml # For parsing LLM structured output
import json # For potentially formatting the body
from utils.api_executor import execute_api_call

class LoadAllSpecs(Node):
    """
    Loads and parses all OpenAPI specifications from the source
    defined in the shared store.
    """
    def prep(self, shared):
        """Reads the openapi_spec_source path/list from the shared store."""
        spec_source = shared.get("openapi_spec_source")
        if not spec_source:
            raise ValueError("'openapi_spec_source' not found in shared store.")
        print(f"LoadAllSpecs: Preparing to load specs from: {spec_source}")
        return spec_source

    def exec(self, spec_source):
        """Calls the utility function to load and parse all specs."""
        print("LoadAllSpecs: Executing spec loading utility...")
        # The actual loading and parsing happens in the utility
        loaded_specs = load_all_specs_from_source(spec_source)
        if not loaded_specs:
            # Even if the utility prints warnings, we might want to raise an error
            # if absolutely no specs could be loaded, as the agent can't proceed.
            raise RuntimeError("Failed to load any OpenAPI specifications.")
        return loaded_specs

    def post(self, shared, prep_res, exec_res):
        """Writes the loaded specs (dict mapping id -> {parsed, summary}) 
           to the shared store."""
        print(f"LoadAllSpecs: Storing {len(exec_res)} loaded specs into shared store.")
        shared["loaded_specs"] = exec_res
        # Transition to the next step in the flow (default action)
        return "default"

class DecomposeQuery(Node):
    """
    Uses an LLM to decompose the user query into a sequence of sub-tasks.
    """
    def prep(self, shared):
        """Reads the user_query from the shared store."""
        user_query = shared.get("user_query")
        if not user_query:
            raise ValueError("'user_query' not found in shared store.")
        print(f"DecomposeQuery: Preparing to decompose query: {user_query}")
        return user_query

    def exec(self, user_query):
        """Calls the LLM to break down the query into steps."""
        prompt = (
            f"Break down the following user request into a sequence of short, actionable, numbered steps. "
            f"Each step should ideally correspond to a single conceptual operation or API call required to fulfill the request. "
            f"Focus on the *actions* needed. Do not add conversational parts or explanations, just the numbered steps.\n"
            f"User Request: \"{user_query}\"\n"
            f"Numbered Steps:"
        )

        print("DecomposeQuery: Calling LLM for task decomposition...")
        llm_response = call_llm(prompt)

        if "LLM_ERROR" in llm_response:
            raise RuntimeError(f"LLM failed during task decomposition: {llm_response}")
        
        print(f"DecomposeQuery: Raw LLM response:\n{llm_response}")
        return llm_response

    def post(self, shared, prep_res, exec_res):
        """Parses the LLM response into a list of task dictionaries 
           and stores it in shared['sub_tasks']."""
        raw_steps = exec_res.strip()
        # Simple parsing: assumes LLM returns numbered lines (e.g., "1. Do X", "2. Do Y")
        # More robust parsing might be needed depending on LLM consistency
        steps = re.findall(r"^\s*\d+\.\s*(.*)", raw_steps, re.MULTILINE)
        
        sub_tasks = []
        if not steps:
             # Handle cases where parsing fails or LLM doesn't follow format
            print("Warning: Could not parse steps from LLM response. Treating response as a single task.")
            if raw_steps: # Avoid adding empty tasks
                 sub_tasks.append({
                    "id": 1,
                    "description": raw_steps, # Use the whole response as one task
                    "status": "pending",
                    "selected_spec_id": None,
                    "api_details": None,
                    "result": None,
                    "error": None
                })
        else:
            for i, step_desc in enumerate(steps):
                sub_tasks.append({
                    "id": i + 1,
                    "description": step_desc.strip(),
                    "status": "pending",
                    "selected_spec_id": None,
                    "api_details": None,
                    "result": None,
                    "error": None
                })

        if not sub_tasks:
             raise RuntimeError("Decomposition resulted in zero tasks.")

        print(f"DecomposeQuery: Storing {len(sub_tasks)} decomposed tasks.")
        shared["sub_tasks"] = sub_tasks
        shared["task_results"] = {} # Initialize task results store
        # Transition to the agent loop start
        return "process_task" 

class SelectSpec(Node):
    """
    Selects the most relevant OpenAPI specification for the current task.
    Acts as the main entry point for the per-task processing loop.
    """
    def prep(self, shared):
        """Finds the next pending task and prepares data for spec selection."""
        sub_tasks = shared.get("sub_tasks", [])
        next_pending_task = None
        for task in sub_tasks:
            if task.get("status") == "pending":
                next_pending_task = task
                break

        if not next_pending_task:
            print("SelectSpec: No more pending tasks found.")
            # No pending tasks left, signal to summarize
            return None # Special value to indicate completion

        shared["current_task_id"] = next_pending_task["id"]
        task_description = next_pending_task["description"]
        loaded_specs = shared.get("loaded_specs", {})

        if not loaded_specs:
            raise RuntimeError("No loaded OpenAPI specs found in shared store to select from.")

        # Format spec summaries for the LLM prompt
        spec_summaries_text = "\n".join([
            f"- ID: {spec_id}\n  Summary: {details.get('summary', 'No summary available.')}"
            for spec_id, details in loaded_specs.items()
        ])

        print(f"SelectSpec: Preparing for task {next_pending_task['id']}: '{task_description}'")
        print(f"SelectSpec: Available Specs:\n{spec_summaries_text}")

        return task_description, spec_summaries_text

    def exec(self, prep_res):
        """Calls the LLM to select the best spec ID based on the task description and summaries."""
        if prep_res is None:
             # This happens if prep found no pending tasks
             return None # Propagate the completion signal
        
        task_description, spec_summaries_text = prep_res

        prompt = (
            f"Given the following task description and available API specification summaries, "
            f"identify the single most relevant API specification ID (e.g., filename) to use for this task. "
            f"Only output the spec ID, nothing else.\n\n"
            f"Task Description:\n{task_description}\n\n"
            f"Available Specifications:\n{spec_summaries_text}\n\n"
            f"Most Relevant Spec ID:"
        )

        print("SelectSpec: Calling LLM for spec selection...")
        llm_response = call_llm(prompt)

        if "LLM_ERROR" in llm_response:
            # Treat LLM error as inability to select a spec for this task
            print(f"Warning: LLM failed during spec selection: {llm_response}")
            return "SPEC_SELECTION_FAILED"
        
        # Clean up the response - expecting just the ID
        selected_spec_id = llm_response.strip()
        print(f"SelectSpec: LLM selected Spec ID: '{selected_spec_id}'")
        return selected_spec_id

    def post(self, shared, prep_res, exec_res):
        """Updates the current task with the selected spec ID or handles errors."""
        if exec_res is None:
            # No more tasks were pending
            return "summarize"

        current_task_id = shared.get("current_task_id")
        if not current_task_id:
            # Should not happen if exec_res is not None, but good practice to check
            raise RuntimeError("current_task_id missing in shared store during SelectSpec post.")

        # Find the current task in the list to update it
        current_task = next((task for task in shared["sub_tasks"] if task["id"] == current_task_id), None)
        if not current_task:
             raise RuntimeError(f"Task with id {current_task_id} not found in shared sub_tasks.")

        selected_spec_id = exec_res
        loaded_specs = shared.get("loaded_specs", {})

        # Validate the selected ID
        if selected_spec_id == "SPEC_SELECTION_FAILED" or selected_spec_id not in loaded_specs:
            print(f"SelectSpec: Failed to select a valid spec for task {current_task_id}. LLM output: '{selected_spec_id}'")
            # Mark task as error and loop back to try the next task
            current_task["status"] = "error"
            current_task["error"] = f"Failed to select a valid spec. LLM response: {selected_spec_id}"
            return "process_task_loop" # Action to loop back to SelectSpec
        else:
            print(f"SelectSpec: Storing selected spec '{selected_spec_id}' for task {current_task_id}.")
            current_task["selected_spec_id"] = selected_spec_id
            # Proceed to the next step for this task
            return "spec_selected"

class FindAndPrepareApi(Node):
    """
    Finds the specific API endpoint within the selected spec for the current task
    and prepares the details needed for execution (method, url, params, body, headers).
    """
    def prep(self, shared):
        """
        Retrieves the current task, its selected spec, and relevant context
        from the shared store.
        """
        current_task_id = shared.get("current_task_id")
        if not current_task_id:
            raise RuntimeError("FindAndPrepareApi: current_task_id missing.")

        current_task = next((task for task in shared.get("sub_tasks", []) if task["id"] == current_task_id), None)
        if not current_task:
            raise RuntimeError(f"FindAndPrepareApi: Task {current_task_id} not found.")

        selected_spec_id = current_task.get("selected_spec_id")
        if not selected_spec_id:
            raise RuntimeError(f"FindAndPrepareApi: Task {current_task_id} has no selected_spec_id.")

        loaded_spec_details = shared.get("loaded_specs", {}).get(selected_spec_id)
        if not loaded_spec_details or "parsed" not in loaded_spec_details:
            raise RuntimeError(f"FindAndPrepareApi: Parsed spec for {selected_spec_id} not found.")

        parsed_spec = loaded_spec_details["parsed"]
        task_description = current_task["description"]
        # Pass previous results - might need refinement later
        previous_results = shared.get("task_results", {})

        print(f"FindAndPrepareApi: Preparing for task {current_task_id}: '{task_description}' using spec '{selected_spec_id}'")

        # Convert spec to string (e.g., YAML) for the LLM prompt
        try:
            # Using YAML dump for potentially better readability for LLM than JSON
            spec_string = yaml.dump(parsed_spec, default_flow_style=False, sort_keys=False)
        except Exception as e:
            print(f"Warning: Could not dump spec {selected_spec_id} to YAML, using repr: {e}")
            spec_string = repr(parsed_spec) # Fallback

        # Pass previous results as JSON string
        context_results_string = json.dumps(previous_results, indent=2) if previous_results else "None"

        return task_description, spec_string, context_results_string, parsed_spec # Pass parsed_spec too for URL construction later

    def exec(self, prep_res):
        """
        Calls the LLM to identify the endpoint, extract parameters, and format
        the necessary details for the API call executor utility.
        """
        task_description, spec_string, context_results_string, parsed_spec = prep_res

        # This prompt is complex and critical. It asks the LLM to act like a tool user.
        # It needs to find the right API call AND extract/fill parameters.
        # Using YAML for structured output from the LLM.
        prompt = f"""
Analyze the following OpenAPI specification and the user task description.
Identify the single best API endpoint (method and path) to fulfill the task.
Determine the necessary parameters (query, path, headers, request body) based on the spec.
Extract parameter values from the task description or the provided context results.
If a required parameter value cannot be found, use the placeholder "<FILL_ME>" for that value.

Task Description:
{task_description}

Context from previous steps (JSON):
{context_results_string}

OpenAPI Specification (YAML):
```yaml
{spec_string[:8000]} # Truncate spec to avoid excessive prompt length
```

Based on the analysis, provide the details for the API call in YAML format below.
Include:
- `method`: The HTTP method (e.g., GET, POST).
- `path`: The endpoint path (e.g., /users/{{userId}}).
- `server_base_url`: The base URL found in the spec's 'servers' section (use the first one if multiple).
- `parameters`: A dictionary containing keys for 'path', 'query', 'header', and 'body'.
  - For 'path', 'query', 'header': map parameter name to its extracted value or "<FILL_ME>".
  - For 'body': provide the structured request body (as a dict) with extracted values or "<FILL_ME>". If no body needed, omit or use null.

```yaml
method: ""
path: ""
server_base_url: ""
parameters:
  path: {{}} # e.g., {{userId: "123"}}
  query: {{}} # e.g., {{limit: 10}}
  header: {{}} # e.g., {{"X-Request-ID": "<FILL_ME>"}}
  body: null # e.g., {{name: "New Item", value: 42}}
```
API Call Details (YAML):
"""
        # Note: Spec truncation might be too aggressive. Consider smarter chunking/filtering
        # or using models with larger context windows if needed.

        print("FindAndPrepareApi: Calling LLM for API details extraction...")
        llm_response = call_llm(prompt)

        if "LLM_ERROR" in llm_response:
            print(f"Error: LLM failed during API detail extraction: {llm_response}")
            return {"error": f"LLM error during API detail extraction: {llm_response}"}

        # Parse the YAML output from the LLM
        try:
            # Extract YAML block
            yaml_output_match = re.search(r"```yaml\n(.*?)```", llm_response, re.DOTALL)
            if not yaml_output_match:
                 # Fallback: Maybe LLM didn't use fences but returned YAML directly
                 yaml_output_str = llm_response.split("API Call Details (YAML):")[-1].strip()
                 if not yaml_output_str:
                     raise ValueError("LLM response did not contain expected YAML block.")
            else:
                 yaml_output_str = yaml_output_match.group(1).strip()

            print(f"FindAndPrepareApi: Raw YAML output from LLM:\n{yaml_output_str}")
            parsed_details = yaml.safe_load(yaml_output_str)

            # Basic validation
            if not isinstance(parsed_details, dict) or not all(k in parsed_details for k in ['method', 'path', 'server_base_url', 'parameters']):
                 raise ValueError("Parsed YAML from LLM is missing required keys.")
            if not isinstance(parsed_details['parameters'], dict):
                 raise ValueError("Parsed 'parameters' key is not a dictionary.")

            # Construct the final api_details for the executor utility
            api_details = {
                "method": parsed_details.get("method", "GET").upper(),
                "url": None, # Will be constructed
                "headers": parsed_details.get("parameters", {}).get("header", {}),
                "params": parsed_details.get("parameters", {}).get("query", {}),
                "body": parsed_details.get("parameters", {}).get("body", None)
            }

            # Construct full URL, handling path parameters
            base_url = parsed_details.get("server_base_url", "")
            if not base_url:
                # Try to extract from spec if LLM missed it
                servers = parsed_spec.get("servers", [])
                if servers and isinstance(servers, list) and "url" in servers[0]:
                    base_url = servers[0]["url"]
                else:
                    return {"error": "Could not determine server base URL from LLM or spec."}

            path_template = parsed_details.get("path", "")
            path_params = parsed_details.get("parameters", {}).get("path", {})
            final_path = path_template
            try:
                # Replace placeholders like {userId} or {{userId}} - simple replace first
                for name, value in path_params.items():
                     if value == "<FILL_ME>":
                          return {"error": f"Required path parameter '{name}' could not be determined."}
                     # Handle common placeholder styles
                     final_path = final_path.replace(f"{{{name}}}", str(value))
                     final_path = final_path.replace(f"{{{{{name}}}}}", str(value)) # Handle double braces just in case
            except Exception as e:
                 return {"error": f"Error substituting path parameters: {e}"}

            api_details["url"] = base_url.rstrip('/') + '/' + final_path.lstrip('/')

            # Potentially add check for unfilled "<FILL_ME>" in params/body/headers
            # For now, we pass them through; executor might handle or fail.

            print(f"FindAndPrepareApi: Prepared API details: {api_details}")
            return api_details

        except Exception as e:
            print(f"Error parsing LLM response or preparing API details: {e}\nLLM Response was:\n{llm_response}")
            return {"error": f"Error parsing LLM response: {e}"}

    def post(self, shared, prep_res, exec_res):
        """Stores the prepared API details in the current task or marks as error."""
        current_task_id = shared.get("current_task_id")
        # Find the current task again (needed because prep_res/exec_res don't contain it)
        current_task = next((task for task in shared["sub_tasks"] if task["id"] == current_task_id), None)

        if not current_task:
             # This really shouldn't happen if prep succeeded
             raise RuntimeError(f"Task {current_task_id} vanished in FindAndPrepareApi post.")

        if isinstance(exec_res, dict) and "error" in exec_res:
            # Error occurred during exec (LLM call, parsing, preparation)
            print(f"FindAndPrepareApi: Error preparing API for task {current_task_id}: {exec_res['error']}")
            current_task["status"] = "error"
            current_task["error"] = exec_res["error"]
            return "process_task_loop" # Loop back to try next task
        elif not isinstance(exec_res, dict) or not exec_res.get("url"):
             # Catch unexpected exec_res format or missing URL
             print(f"FindAndPrepareApi: Invalid API details prepared for task {current_task_id}: {exec_res}")
             current_task["status"] = "error"
             current_task["error"] = f"Invalid API details prepared: {exec_res}"
             return "process_task_loop"
        else:
            # Success - store the details
            print(f"FindAndPrepareApi: Storing prepared API details for task {current_task_id}.")
            current_task["api_details"] = exec_res
            return "execute" # Proceed to execute this task

class ExecuteAPI(Node):
    """
    Executes the API call prepared by the FindAndPrepareApi node.
    """
    def prep(self, shared):
        """Retrieves the prepared API details for the current task."""
        current_task_id = shared.get("current_task_id")
        if not current_task_id:
            raise RuntimeError("ExecuteAPI: current_task_id missing.")

        current_task = next((task for task in shared.get("sub_tasks", []) if task["id"] == current_task_id), None)
        if not current_task:
            raise RuntimeError(f"ExecuteAPI: Task {current_task_id} not found.")

        api_details = current_task.get("api_details")
        if not api_details or not isinstance(api_details, dict) or not api_details.get("url"):
             # This implies an error in the previous node or flow logic
             raise RuntimeError(f"ExecuteAPI: Invalid or missing api_details for task {current_task_id}.")

        print(f"ExecuteAPI: Preparing to execute API for task {current_task_id}")
        return api_details

    def exec(self, api_details):
        """Calls the execute_api_call utility function."""
        print(f"ExecuteAPI: Calling executor utility for URL: {api_details.get('url')}")
        # The actual API call is handled by the utility
        result = execute_api_call(api_details)
        return result

    def post(self, shared, prep_res, exec_res):
        """Updates the task status, stores results/errors, and loops back."""
        current_task_id = shared.get("current_task_id")
        # Find the current task again
        current_task = next((task for task in shared["sub_tasks"] if task["id"] == current_task_id), None)
        if not current_task:
             raise RuntimeError(f"Task {current_task_id} vanished in ExecuteAPI post.")

        api_result = exec_res # Result from the execute_api_call utility

        # Check if the API call was successful
        # Basic check: status code 2xx and no error reported by utility
        is_success = (
            api_result.get("status_code") is not None and 
            200 <= api_result.get("status_code") < 300 and 
            api_result.get("error") is None
        )

        if is_success:
            print(f"ExecuteAPI: Task {current_task_id} completed successfully (Status: {api_result.get('status_code')}).")
            current_task["status"] = "completed"
            current_task["result"] = api_result.get("body")
            current_task["error"] = None
            # Store successful result for potential use by later tasks
            shared.setdefault("task_results", {})[current_task_id] = api_result.get("body")
        else:
            error_msg = api_result.get("error", "Unknown API execution error")
            status_code = api_result.get("status_code", "N/A")
            error_body = api_result.get("body", "") # Include body in error if available
            full_error = f"API Call Failed (Status: {status_code}): {error_msg}. Response Body: {str(error_body)[:200]}..."
            print(f"ExecuteAPI: Task {current_task_id} failed: {full_error}")
            current_task["status"] = "error"
            current_task["result"] = None
            current_task["error"] = full_error
        
        # Always loop back to SelectSpec to process the next task or finish
        return "process_task_loop"

class SummarizeResults(Node):
    """
    Summarizes the results collected from all successful API calls.
    """
    def prep(self, shared):
        """Retrieves the original query and all successful task results."""
        user_query = shared.get("user_query", "No query provided")
        task_results = shared.get("task_results", {})
        sub_tasks = shared.get("sub_tasks", [])

        print("SummarizeResults: Preparing to summarize results.")

        # Format results for the LLM prompt, including task description for context
        formatted_results = []
        if not task_results:
            formatted_results_str = "No successful task results were obtained."
        else:
            for task in sub_tasks:
                task_id = task["id"]
                if task_id in task_results:
                    # Found a successful result for this task
                    result_data = task_results[task_id]
                    try:
                        result_str = json.dumps(result_data, indent=2)
                    except TypeError:
                        result_str = str(result_data) # Fallback if not JSON serializable
                    
                    formatted_results.append(
                        f"Task {task_id}: {task.get('description', 'N/A')}\nResult:\n```json\n{result_str}\n```"
                    )
            formatted_results_str = "\n\n".join(formatted_results) 
            if not formatted_results_str:
                 formatted_results_str = "No successful task results found to format (check task_results structure)."

        print(f"SummarizeResults: Formatted results for LLM:\n{formatted_results_str}")
        return user_query, formatted_results_str

    def exec(self, prep_res):
        """Calls the LLM to generate a summary."""
        user_query, formatted_results_str = prep_res

        prompt = (
            f"Based on the original user request and the results obtained from the executed tasks, "
            f"provide a concise summary answering the user's request. "
            f"Integrate the relevant information from the task results naturally. "
            f"If no relevant results were found or tasks failed, state that clearly.\n\n"
            f"Original User Request:\n{user_query}\n\n"
            f"Results from Executed Tasks:\n{formatted_results_str}\n\n"
            f"Final Summary:"
        )

        print("SummarizeResults: Calling LLM for final summarization...")
        summary = call_llm(prompt)

        if "LLM_ERROR" in summary:
            # If summarization fails, provide a basic fallback
            print(f"Warning: LLM failed during summarization: {summary}")
            summary = f"Could not generate summary due to LLM error. Results obtained: {formatted_results_str}"

        return summary

    def post(self, shared, prep_res, exec_res):
        """Stores the final summary in the shared store."""
        final_summary = exec_res
        print(f"SummarizeResults: Storing final summary:\n{final_summary}")
        shared["final_summary"] = final_summary
        # Return None to indicate the end of the flow
        return None

# --- End of Node definitions --- #
