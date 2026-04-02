"""Compatibility wrapper for the renamed fog-layer generator.

The EC2 service and older scripts still invoke generate_sensors.py.
This wrapper preserves that entrypoint while the real implementation
lives in Fog_node.py.
"""

from Fog_node import main


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)