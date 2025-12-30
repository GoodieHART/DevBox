import modal

app = modal.App(name="test-windows-sandbox")


@app.function()
def test_windows_sandbox():
    """Simple test function to verify Windows sandbox creation works."""
    print("Testing Windows sandbox creation...")

    # Simple test sandbox
    windows_image = modal.Image.from_registry("dockurr/windows:latest")
    sandbox = modal.Sandbox.create(
        image=windows_image,
        cpu=2.0,
        memory=4096,  # 4GB
        timeout=300,  # 5 minutes for testing
        unencrypted_ports=[3389, 8006],
    )

    print("Sandbox created successfully!")
    print(f"Sandbox ID: {sandbox.object_id}")

    # Wait a bit for it to start
    import time

    time.sleep(5)

    # Try to get tunnels
    try:
        tunnels = sandbox.tunnels(timeout=30)
        print("Tunnels established:")
        for port, tunnel in tunnels.items():
            print(f"  Port {port}: {tunnel.host}:{tunnel.port}")
    except Exception as e:
        print(f"Tunnel setup failed: {e}")

    return f"Test completed. Sandbox: {sandbox.object_id}"


@app.local_entrypoint()
def main():
    with app.run():
        result = test_windows_sandbox.remote()
        print(f"Result: {result}")
