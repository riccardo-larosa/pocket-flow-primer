import os
import yaml
import glob
from typing import Dict, List, Union

def load_all_specs_from_source(spec_source: Union[str, List[str]]) -> Dict[str, Dict[str, Union[dict, str]]]:
    """
    Loads OpenAPI specifications from a directory or a list of file paths,
    parses them, and generates a simple summary (placeholder).

    Args:
        spec_source: Either a directory path containing spec files (*.yaml, *.yml, *.json)
                     or a list of specific file paths.

    Returns:
        A dictionary mapping the spec filename (or a generated ID) to its
        parsed content and a placeholder summary.
        Example: { "products.yaml": {"parsed": {...}, "summary": "Spec: products.yaml"} }
    """
    loaded_specs = {}
    spec_files = []

    if isinstance(spec_source, str) and os.path.isdir(spec_source):
        # Find specs in directory
        patterns = ['*.yaml', '*.yml', '*.json']
        for pattern in patterns:
            spec_files.extend(glob.glob(os.path.join(spec_source, pattern)))
    elif isinstance(spec_source, list):
        # Use provided list of files
        spec_files = spec_source
    else:
        raise ValueError("spec_source must be a directory path or a list of file paths")

    for spec_path in spec_files:
        if not os.path.isfile(spec_path):
            print(f"Warning: Specified spec file not found: {spec_path}")
            continue
        try:
            with open(spec_path, 'r', encoding='utf-8') as f:
                parsed_content = yaml.safe_load(f)
            # Use filename as identifier
            spec_id = os.path.basename(spec_path)
            # Placeholder summary - Needs improvement (e.g., using LLM or extracting info)
            summary = f"Spec: {spec_id} - Title: {parsed_content.get('info', {}).get('title', 'N/A')}"
            loaded_specs[spec_id] = {
                "parsed": parsed_content,
                "summary": summary
            }
            print(f"Loaded spec: {spec_id}")
        except Exception as e:
            print(f"Error loading or parsing spec {spec_path}: {e}")

    if not loaded_specs:
        print("Warning: No OpenAPI specifications were successfully loaded.")

    return loaded_specs

# Example usage (for testing)
if __name__ == "__main__":
    # Create dummy spec files for testing
    dummy_dir = "temp_specs"
    os.makedirs(dummy_dir, exist_ok=True)
    dummy_spec1 = os.path.join(dummy_dir, "products.yaml")
    dummy_spec2 = os.path.join(dummy_dir, "orders.json")

    spec1_content = """
openapi: 3.0.0
info:
  title: Product API
  version: 1.0.0
paths:
  /products:
    get:
      summary: List all products
"""
    spec2_content = """
{
  "openapi": "3.0.0",
  "info": {
    "title": "Orders API",
    "version": "1.0.0"
  },
  "paths": {
    "/orders": {
      "post": {
        "summary": "Create a new order"
      }
    }
  }
}
"""
    with open(dummy_spec1, 'w') as f:
        f.write(spec1_content)
    with open(dummy_spec2, 'w') as f:
        f.write(spec2_content)

    print("--- Testing loading from directory ---")
    specs_from_dir = load_all_specs_from_source(dummy_dir)
    print(specs_from_dir)
    assert "products.yaml" in specs_from_dir
    assert "orders.json" in specs_from_dir
    assert "summary" in specs_from_dir["products.yaml"]

    print("\n--- Testing loading from list ---")
    specs_from_list = load_all_specs_from_source([dummy_spec1, "nonexistent.yaml"])
    print(specs_from_list)
    assert "products.yaml" in specs_from_list
    assert len(specs_from_list) == 1

    # Clean up dummy files
    # import shutil
    # shutil.rmtree(dummy_dir)
    print("\nCleanup: Manual cleanup of 'temp_specs' directory might be needed.")
