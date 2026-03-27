"""Submit a ComfyUI workflow via API and wait for completion."""
import json
import sys
import time
import urllib.request
import urllib.error
import uuid

SERVER = "http://127.0.0.1:8188"

def queue_prompt(prompt_data):
    """Queue a prompt and return the prompt_id."""
    client_id = str(uuid.uuid4())
    payload = json.dumps({"prompt": prompt_data, "client_id": client_id}).encode()
    req = urllib.request.Request(f"{SERVER}/prompt", data=payload,
                                headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    return result["prompt_id"]

def wait_for_completion(prompt_id, timeout=300):
    """Poll /history until the prompt completes."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = urllib.request.urlopen(f"{SERVER}/history/{prompt_id}")
            history = json.loads(resp.read())
            if prompt_id in history:
                return history[prompt_id]
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"Workflow did not complete within {timeout}s")

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_workflow.py <workflow.json>")
        sys.exit(1)

    workflow_path = sys.argv[1]
    with open(workflow_path) as f:
        data = json.load(f)

    # Support both {"prompt": {...}} and raw node dict
    prompt_data = data.get("prompt", data)

    print(f"Submitting workflow: {workflow_path}")
    prompt_id = queue_prompt(prompt_data)
    print(f"Queued prompt_id: {prompt_id}")
    print("Waiting for completion...")

    result = wait_for_completion(prompt_id)
    status = result.get("status", {})
    if status.get("status_str") == "error":
        print("WORKFLOW FAILED!")
        msgs = status.get("messages", [])
        for m in msgs:
            print(f"  {m}")
        sys.exit(1)

    outputs = result.get("outputs", {})
    for node_id, node_out in outputs.items():
        if "images" in node_out:
            for img in node_out["images"]:
                print(f"Saved: {img['subfolder']}/{img['filename']}" if img.get('subfolder') else f"Saved: {img['filename']}")

    print("Done!")

if __name__ == "__main__":
    main()
