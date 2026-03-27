"""Run a Deforum workflow by auto-queuing once per frame."""
import json
import sys
import time
import urllib.request
import urllib.error
import uuid

SERVER = "http://127.0.0.1:8188"

def queue_prompt(prompt_data, client_id):
    payload = json.dumps({"prompt": prompt_data, "client_id": client_id}).encode()
    req = urllib.request.Request(f"{SERVER}/prompt", data=payload,
                                headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())["prompt_id"]

def wait_for_completion(prompt_id, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = urllib.request.urlopen(f"{SERVER}/history/{prompt_id}")
            history = json.loads(resp.read())
            if prompt_id in history:
                status = history[prompt_id].get("status", {})
                if status.get("status_str") == "error":
                    msgs = status.get("messages", [])
                    print(f"  ERROR: {msgs}")
                    return False
                return True
        except Exception:
            pass
        time.sleep(1)
    print("  TIMEOUT!")
    return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_deforum.py <workflow.json> [num_frames]")
        sys.exit(1)

    workflow_path = sys.argv[1]
    with open(workflow_path) as f:
        data = json.load(f)

    prompt_data = data.get("prompt", data)

    # Get max_frames from the workflow or command line
    num_frames = int(sys.argv[2]) if len(sys.argv) > 2 else 120

    # Look for max_frames in DeforumAnimParamsNode and update it
    for node_id, node in prompt_data.items():
        if node.get("class_type") == "DeforumAnimParamsNode":
            if "max_frames" in node.get("inputs", {}):
                node["inputs"]["max_frames"] = num_frames
                print(f"Set max_frames={num_frames} in node {node_id}")

    client_id = str(uuid.uuid4())
    print(f"Starting Deforum animation: {num_frames} frames")
    print(f"Client ID: {client_id}")

    start_time = time.time()
    for frame in range(num_frames):
        t0 = time.time()
        prompt_id = queue_prompt(prompt_data, client_id)
        success = wait_for_completion(prompt_id)
        elapsed = time.time() - t0
        if success:
            print(f"  Frame {frame+1}/{num_frames} done ({elapsed:.1f}s)")
        else:
            print(f"  Frame {frame+1}/{num_frames} FAILED - stopping")
            break

    total = time.time() - start_time
    print(f"\nDone! {num_frames} frames in {total:.1f}s ({total/num_frames:.1f}s/frame avg)")

if __name__ == "__main__":
    main()
