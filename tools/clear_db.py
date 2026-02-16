#!/usr/bin/env python
"""
Database cleanup script for AloneChat.

Clears all user data from both JSON file and ClickHouse.
"""

import os
import sys
import json

def clear_json_db():
    """Clear JSON user database."""
    db_file = "user_credentials.json"
    
    if os.path.exists(db_file):
        try:
            with open(db_file, 'w') as f:
                json.dump({}, f)
            print(f"✓ Cleared JSON database: {db_file}")
            return True
        except Exception as e:
            print(f"✗ Failed to clear JSON database: {e}")
            return False
    else:
        print(f"○ JSON database not found: {db_file}")
        return True


def clear_clickhouse():
    """Clear ClickHouse tables."""
    try:
        from AloneChat.config import config
        
        if not config.CLICKHOUSE_ENABLED:
            print("○ ClickHouse not enabled, skipping")
            return True
        
        from clickhouse_driver import Client
        
        client = Client(
            host=config.CLICKHOUSE_HOST,
            port=config.CLICKHOUSE_PORT,
            user=config.CLICKHOUSE_USER,
            password=config.CLICKHOUSE_PASSWORD,
            database=config.CLICKHOUSE_DATABASE,
        )
        
        tables = ['users', 'user_sessions', 'user_activity']
        
        for table in tables:
            try:
                client.execute(f"TRUNCATE TABLE IF EXISTS {table}")
                print(f"✓ Truncated ClickHouse table: {table}")
            except Exception as e:
                print(f"○ Table {table} not found or already empty")
        
        return True
    
    except ImportError:
        print("○ clickhouse-driver not installed, skipping ClickHouse")
        return True
    except Exception as e:
        print(f"✗ Failed to clear ClickHouse: {e}")
        return False


def clear_feedback():
    """Clear feedback file."""
    feedback_file = "feedback.json"
    
    if os.path.exists(feedback_file):
        try:
            with open(feedback_file, 'w') as f:
                json.dump({"feedbacks": []}, f)
            print(f"✓ Cleared feedback file: {feedback_file}")
            return True
        except Exception as e:
            print(f"✗ Failed to clear feedback file: {e}")
            return False
    else:
        print(f"○ Feedback file not found: {feedback_file}")
        return True


def main():
    print("=" * 50)
    print("AloneChat Database Cleanup")
    print("=" * 50)
    
    results = []
    
    print("\n[1/3] Clearing JSON database...")
    results.append(clear_json_db())
    
    print("\n[2/3] Clearing ClickHouse...")
    results.append(clear_clickhouse())
    
    print("\n[3/3] Clearing feedback...")
    results.append(clear_feedback())
    
    print("\n" + "=" * 50)
    if all(results):
        print("✓ All databases cleared successfully!")
    else:
        print("⚠ Some operations failed, check output above")
    print("=" * 50)


if __name__ == "__main__":
    main()
