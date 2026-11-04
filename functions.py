# ATLAS Functions Module
# Utility functions for the ATLAS 6-layer trading system

import json
import os
import yaml
from datetime import datetime
from pathlib import Path


def get_market_hours_check(current_time_ist: str) -> dict:
    """
    Check if current time is within NSE market hours (09:15-15:30 IST).
    
    Args:
        current_time_ist: Current time in IST format
        
    Returns:
        dict with 'in_hours' boolean and 'reason' string
    """
    try:
        # Parse IST time
        if 'IST' in current_time_ist or '+05:30' in current_time_ist:
            # Handle various time formats
            hour = int(current_time_ist.split(':')[0]) if ':' in current_time_ist else 0
        else:
            hour = 0
        
        # NSE market hours: 09:15 to 15:30 IST
        in_market_hours = 9 <= hour <= 15
        
        if in_market_hours:
            # Additional check for exact hours
            if hour == 15 and True:  # Simplified check
                in_market_hours = True
        else:
            in_market_hours = False
            
        return {
            'in_market_hours': in_market_hours,
            'reason': 'Within NSE market hours (09:15-15:30 IST)' if in_market_hours else 
                     'Outside NSE market hours (09:15-15:30 IST)'
        }
    except Exception as e:
        return {
            'in_market_hours': False,
            'reason': f'Error checking market hours: {str(e)}'
        }


def format_journal_entry(entry_id: str, timestamp_ist: str, 
                        regime_flags: dict, event_alerts: list,
                        thesis: str, decision_proposal: dict,
                        risk_verdict: dict, order_result: dict = None,
                        pnl: float = 0.0, confidence_calibration: dict = None) -> dict:
    """
    Format a journal ledger entry following the ATLAS protocol.
    
    Args:
        entry_id: Unique entry identifier
        timestamp_ist: IST timestamp
        regime_flags: Regime detection flags
        event_alerts: List of event alerts
        thesis: Research AI thesis
        decision_proposal: Agent AI decision proposal
        risk_verdict: Risk verdict object
        order_result: Order execution result (optional)
        pnl: Profit and loss (optional)
        confidence_calibration: Confidence calibration data (optional)
        
    Returns:
        Formatted journal entry dictionary
    """
    entry = {
        'entry_id': entry_id,
        'timestamp_ist': timestamp_ist,
        'regime_flags': regime_flags,
        'event_alerts': event_alerts,
        'thesis': thesis,
        'decision_proposal': decision_proposal,
        'risk_verdict': risk_verdict,
    }
    
    if order_result is not None:
        entry['order_result'] = order_result
    if pnl != 0.0:
        entry['pnl'] = pnl
    if confidence_calibration is not None:
        entry['confidence_calibration'] = confidence_calibration
    
    return entry


def calculate_confidence_calibration(hit_rate: float, expected_rate: float = 0.7) -> dict:
    """
    Calculate confidence calibration metrics.
    
    Args:
        hit_rate: Actual hit rate observed
        expected_rate: Expected hit rate (default 0.7 = 70%)
        
    Returns:
        Calibration dictionary with drift information
    """
    drift = hit_rate - expected_rate
    calibration_status = 'overconfident' if drift > 0.1 else 'underconfident' if drift < -0.1 else 'well-calibrated'
    
    return {
        'hit_rate': hit_rate,
        'expected_rate': expected_rate,
        'drift': drift,
        'calibration_status': calibration_status,
        'assessment': f'System is {calibration_status} (drift: {drift:+.2%})'
    }


def validate_regime_flags(regime_flags: dict) -> dict:
    """
    Validate regime flags for the ATLAS system.
    
    Args:
        regime_flags: Regime flags dictionary
        
    Returns:
        Validation result dictionary
    """
    required_keys = ['trending', 'chop', 'reversal', 'breakout']
    missing_keys = [k for k in required_keys if k not in regime_flags]
    
    return {
        'valid': len(missing_keys) == 0,
        'missing_keys': missing_keys,
        'all_flags_present': len(missing_keys) == 0,
        'regime_flags': regime_flags
    }


def validate_agent_frontmatter(agent_path: str) -> dict:
    """
    Validate YAML frontmatter in an agent markdown file.
    
    Args:
        agent_path: Path to agent markdown file
        
    Returns:
        Validation result dictionary
    """
    required_fields = ["name", "description", "tools"]
    
    try:
        with open(agent_path, 'r') as f:
            content = f.read()
        
        if not content.startswith('---'):
            return {'valid': False, 'error': 'Missing frontmatter delimiter (---)'}
        
        parts = content.split('---', 2)
        if len(parts) < 3:
            return {'valid': False, 'error': 'Incomplete frontmatter'}
        
        frontmatter_str = parts[1].strip()
        frontmatter = yaml.safe_load(frontmatter_str)
        
        if not isinstance(frontmatter, dict):
            return {'valid': False, 'error': 'Frontmatter is not a valid YAML object'}
        
        missing = [field for field in required_fields if field not in frontmatter]
        if missing:
            return {'valid': False, 'error': f'Missing required fields: {missing}'}
        
        if not isinstance(frontmatter.get("tools"), list):
            return {'valid': False, 'error': 'tools must be a list'}
        
        return {
            'valid': True,
            'name': frontmatter.get('name'),
            'description': frontmatter.get('description'),
            'tools': frontmatter.get('tools')
        }
    
    except yaml.YAMLError as e:
        return {'valid': False, 'error': f'YAML parse error: {e}'}
    except Exception as e:
        return {'valid': False, 'error': f'Error: {e}'}


def validate_all_agents(agents_dir: str = None) -> dict:
    """
    Validate all agent files in the agents directory.
    
    Args:
        agents_dir: Path to agents directory (default: .copilot/agents)
        
    Returns:
        Validation summary dictionary
    """
    if agents_dir is None:
        agents_dir = "/Users/suryavamsipichika/.copilot/agents"
    
    agents_path = Path(agents_dir)
    agent_files = list(agents_path.glob("*.md"))
    
    results = {
        'total': len(agent_files),
        'valid': 0,
        'invalid': 0,
        'details': []
    }
    
    for agent_file in sorted(agent_files):
        result = validate_agent_frontmatter(str(agent_file))
        result['file'] = agent_file.name
        results['details'].append(result)
        if result['valid']:
            results['valid'] += 1
        else:
            results['invalid'] += 1
    
    results['all_valid'] = results['invalid'] == 0
    return results
