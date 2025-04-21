---
layout: default
title: "API Agent System Design"
---

# Design Document: API Agent System

This document outlines the design for a system that understands user queries, decomposes them into tasks, uses an OpenAPI specification to find and execute relevant API calls for each task, and summarizes the results.

## 1. Requirements

*   **Problem:** Users need to perform multi-step operations that involve querying various APIs, but they want to express their needs in natural language without needing to know the specific API endpoints or sequence them manually.
*   **Goal:** Build a system that takes a user query and one or more OpenAPI specifications, automatically breaks down the query, finds and executes the necessary API calls sequentially (selecting the correct spec for each step), and provides a final summary of the results.
*   **Inputs:**
    *   `user_query`: A string containing the user's request in natural language.
    *   `openapi_spec_source`: A string indicating either a directory containing multiple spec files or a list of specific file paths.
*   **Output:**
    *   `final_summary`: A string summarizing the results obtained from the executed API calls, relevant to the initial user query.
*   **Key Capabilities:**
    *   Natural Language Understanding (NLU) for query decomposition.
    *   Selection of the most relevant OpenAPI specification for a given task.
    *   Searching/Matching within a *specific* OpenAPI specification to find appropriate endpoints.
    *   Sequential task execution and state management.
    *   Dynamic API call execution based on the specification.
    *   Result aggregation and summarization.

## 2. Flow Design

*   **Pattern:** An **Agent** pattern is most suitable due to the dynamic decision-making required (choosing tasks, selecting specs, finding APIs, handling results sequentially). The agent orchestrates the process step-by-step.
*   **High-Level Node Descriptions:**
    1.  `LoadAllSpecs`: Loads and parses *all* OpenAPI specifications found in the specified source, generating a concise summary for each.
    2.  `DecomposeQuery`: Uses an LLM to break the initial user query into a list of sequential, actionable sub-tasks.
    3.  `SelectSpec`: For the current sub-task, uses an LLM to determine which *specific* OpenAPI spec file is most likely to contain the needed endpoint, based on task description and spec summaries.
    4.  `FindAndPrepareApi`: Takes the *selected* spec, finds the specific endpoint within it for the task using an LLM, and prepares the necessary call details (parameters, body).
    5.  `ExecuteAPI`: Executes the prepared API call using a utility function.
    6.  `SummarizeResults`: Once all tasks are completed or cannot proceed, uses an LLM to synthesize the collected results into a final summary based on the original query.
*   **Flow Diagram:**

    ```mermaid
    flowchart TD
        Start[User Query + OpenAPI Spec Source] --> LoadAllSpecs[Load & Summarize All Specs]
        LoadAllSpecs --> DecomposeQuery[Decompose Query into Sub-Tasks (LLM)]
        DecomposeQuery --> ProcessTask{Agent: Process Next Task?}

        ProcessTask -- Yes, Task Found --> SelectSpec[Select Relevant Spec (LLM)]
        SelectSpec -- Spec Selected --> FindAndPrepareApi[Find API in Selected Spec & Prepare Call (LLM)]
        SelectSpec -- Spec Not Found/Error --> HandleSpecError[Log Error/Skip Task]
        HandleSpecError --> ProcessTask

        FindAndPrepareApi -- API Found & Prepared --> ExecuteAPI[Execute API Call (Utility)]
        FindAndPrepareApi -- API Not Found/Error --> HandleApiError[Log Error/Skip Task]
        HandleApiError --> ProcessTask

        ExecuteAPI -- Success/Error --> ProcessTask
        ProcessTask -- No More Tasks --> SummarizeResults[Summarize All Results (LLM)]
        SummarizeResults --> End[Final Summary]
    ```
    *(Note: ProcessTask represents the main agent loop control point. Error handling paths lead back to the loop to attempt the next task.)*

## 3. Utilities

The following external utility functions are required:

1.  **`call_llm(prompt: str, context: Any = None) -> str`** (`utils/call_llm.py`)
    *   **Input:** Prompt string, optional context (e.g., previous messages, system instructions).
    *   **Output:** String response from the LLM.
    *   **Necessity:** Core component for NLU, task decomposition, spec selection, API matching, parameter preparation (potentially), and final summarization.
2.  **`load_all_specs_from_source(spec_source: str) -> dict`** (`utils/openapi_parser.py`)
    *   **Input:** Directory path or list of file paths.
    *   **Output:** A dictionary mapping a spec identifier (e.g., filename) to a dictionary containing its parsed content and a concise summary. Example: `{ "products.yaml": {"parsed": {...}, "summary": "Manage products..."} }`
    *   **Necessity:** Required by `LoadAllSpecs` to load, parse, and summarize all available specs for later selection.
3.  **`execute_api_call(api_details: dict) -> dict`** (`utils/api_executor.py`)
    *   **Input:** Dictionary containing method, URL, headers, parameters, body for the API call.
    *   **Output:** Dictionary containing the API response status, body, and any errors.
    *   **Necessity:** Required by the `ExecuteAPI` node to interact with the actual external APIs defined in the spec.

*(Each utility should be implemented with a simple test under `if __name__ == "__main__":`)*

## 4. Node Design

*   **Shared Store Structure:**
    ```python
    shared = {
        "user_query": "User's original request string",
        "openapi_spec_source": "/path/to/specs/dir", # or ["/path/specs1.yaml", ...]
        "loaded_specs": {
            # Dict mapping spec identifier to its parsed content and summary
            # Example: "products_api.yaml": {"parsed": {...}, "summary": "API for products..."}
        },
        "sub_tasks": [
            # List of dicts representing decomposed tasks
            # Example: {'id': 1, 'description': 'Find user ID for "John Doe"', 'status': 'pending'|'completed'|'error', 'selected_spec_id': None, 'api_details': {...}, 'result': {...}, 'error': '...' }
        ],
        "task_results": {
            # Dictionary mapping task_id to its successful result for cross-task reference
            # Example: {1: {'userId': 'johndoe123'}}
         },
        "current_task_id": 1, # ID of the task currently being processed
        "final_summary": "Final summary string"
    }
    ```
*   **Node Descriptions (High-Level):**
    *   **`LoadAllSpecs` (Node):**
        *   `prep`: Reads `openapi_spec_source` from `shared`.
        *   `exec`: Calls `load_all_specs_from_source` utility.
        *   `post`: Writes the resulting dictionary to `shared["loaded_specs"]`. Returns `"default"`.
    *   **`DecomposeQuery` (Node):**
        *   `prep`: Reads `user_query` from `shared`.
        *   `exec`: Calls `call_llm` to break query into actionable steps.
        *   `post`: Populates `shared["sub_tasks"]` with task dictionaries (initially `status='pending'`). Returns `"process_task"`.
    *   **`SelectSpec` (Node):**
        *   `prep`: Finds the next task with `status == 'pending'` in `shared["sub_tasks"]`. Sets `shared["current_task_id"]`. If no task found, returns `None`. If task found, reads its description and the summaries from `shared["loaded_specs"]`.
        *   `exec`: If task exists, calls `call_llm` asking it to choose the *best spec identifier* (e.g., filename) from the summaries based on the task description.
        *   `post`: If `prep` found no task, returns `"summarize"`. If LLM selected a spec, updates the current task's `selected_spec_id` in `shared` and returns `"spec_selected"`. If LLM fails/cannot choose, marks task as 'error' and returns `"process_task_loop"`.
    *   **`FindAndPrepareApi` (Node):**
        *   `prep`: Reads the current task's description and `selected_spec_id`. Fetches the corresponding *parsed* spec from `shared["loaded_specs"]`. Reads relevant data from `shared["task_results"]`.
        *   `exec`: Calls `call_llm` with the task description and the *selected parsed spec* to find the specific API endpoint (method, path, parameters). Determines parameters/body needed using spec and available data. Constructs full `api_details`.
        *   `post`: Updates task's `api_details` in `shared`. If successful, returns `"execute"`. If API not found or preparation fails, marks task as 'error', returns `"process_task_loop"`.
    *   **`ExecuteAPI` (Node):**
        *   `prep`: Reads prepared `api_details` for the current task from `shared`.
        *   `exec`: Calls `execute_api_call` utility.
        *   `post`: Updates task `status` ('completed' or 'error'), `result`/`error` fields in `shared["sub_tasks"]`. If successful, adds result to `shared["task_results"]`. Returns `"process_task_loop"`.
    *   **`SummarizeResults` (Node):**
        *   `prep`: Reads `user_query` and collects all successful results from `shared["task_results"]`.
        *   `exec`: Calls `call_llm` to generate a summary based on the query and results.
        *   `post`: Writes summary to `shared["final_summary"]`. Returns `None`.

## 5. Implementation Notes

*   Start with a minimal implementation. The separation between `SelectSpec` and `FindAndPrepareApi` is recommended.
*   Focus on clear prompting for LLM-based nodes, especially for spec selection and API finding within the selected spec.
*   Use extensive logging for debugging.
*   Implement `flow.py` connecting the nodes based on the actions defined above (e.g., `SelectSpec - "spec_selected" >> FindAndPrepareApi`, `ExecuteAPI - "process_task_loop" >> SelectSpec`).
*   Create `main.py` as the entry point.

## 6. Optimization Considerations

*   **Prompt Engineering:** Iteratively refine prompts for decomposition, spec selection, API matching, and summarization.
*   **Spec Summarization:** Ensure the generated summaries in `LoadAllSpecs` are effective for the `SelectSpec` LLM call. Consider different summary levels or keyword extraction.
*   **Context Management:** Ensure only relevant previous results are passed to subsequent tasks or the final summarizer.
*   **API Spec Caching:** Cache parsed specs and summaries if loading is slow.
*   **LLM Caching:** Implement caching for LLM calls (with awareness of retry logic).

## 7. Reliability Considerations

*   **Error Handling:** Implement robust error handling in `execute_api_call` utility and the `ExecuteAPI` node.
*   **Fallback Logic:** Define behavior in `SelectSpec` (if no spec can be chosen) and `FindAndPrepareApi` (if API not found in chosen spec). Options: skip task, ask user, try a default spec.
*   **Validation:** Add checks to validate LLM outputs (e.g., does the selected spec ID exist? Does the identified API exist in that spec?).
*   **Retries:** Use `max_retries` and `wait` parameters on Nodes calling LLMs or external APIs.
*   **Logging:** Implement comprehensive logging.
