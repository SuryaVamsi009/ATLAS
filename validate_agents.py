#!/usr/bin/env python3
"""
Agent Validation Script for ATLAS
Validates YAML frontmatter and tests agent loading for all agents in .copilot/agents/
"""

import yaml
import os
import sys
from pathlib import Path

AGENTS_DIR = Path(__file__).parent / ".github" / "agents"
REQUIRED_FIELDS = ["name", "description", "tools"]

def validate_frontmatter(filepath):
    """Validate YAML frontmatter in agent markdown file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Check if file starts with ---
        if not content.startswith('---'):
            return False, "Missing frontmatter delimiter (---)"
        
        # Extract frontmatter
        parts = content.split('---', 2)
        if len(parts) < 3:
            return False, "Incomplete frontmatter"
        
        frontmatter_str = parts[1].strip()
        frontmatter = yaml.safe_load(frontmatter_str)
        
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter is not a valid YAML object"
        
        # Check required fields
        missing = [field for field in REQUIRED_FIELDS if field not in frontmatter]
        if missing:
            return False, f"Missing required fields: {missing}"
        
        # Validate tools is a list
        if not isinstance(frontmatter.get("tools"), list):
            return False, "tools must be a list"
        
        return True, f"Valid: {frontmatter.get('name')}"
    
    except yaml.YAMLError as e:
        return False, f"YAML parse error: {e}"
    except Exception as e:
        return False, f"Error: {e}"

def validate_all_agents():
    """Validate all agent files in the agents directory."""
    print(f"Validating agents in: {AGENTS_DIR}")
    print("=" * 60)
    
    agent_files = list(AGENTS_DIR.glob("*.md"))
    if not agent_files:
        print("No agent files found!")
        return False
    
    all_valid = True
    for agent_file in sorted(agent_files):
        valid, msg = validate_frontmatter(agent_file)
        status = "✅" if valid else "❌"
        print(f"{status} {agent_file.name}: {msg}")
        if not valid:
            all_valid = False
    
    print("=" * 60)
    if all_valid:
        print("All agents have valid frontmatter!")
    else:
        print("Some agents have invalid frontmatter!")
    
    return all_valid

def test_agent_loading():
    """Test that agents can be loaded (placeholder for actual load test)."""
    print("\nTesting agent loading...")
    print("Note: Actual load test requires Copilot CLI/UI")
    print("Run: copilot agent list  # to verify agents load")
    return True

if __name__ == "__main__":
    print("ATLAS Agent Validation")
    print("=" * 60)
    
    valid = validate_all_agents()
    test_agent_loading()
    
    sys.exit(0 if valid else 1)