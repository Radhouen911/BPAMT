#!/usr/bin/env python3
"""
CTFd Task Deployment Script
Deploys CTF tasks from a directory to a CTFd instance with credential management.

Developed by Angel911
"""

import os
import json
import requests 
import argparse
import sys
from pathlib import Path
from typing import Dict, Optional, List
import yaml
import zipfile
import tempfile

class CTFdDeployer:
    def __init__(self):
        self.config_file = Path.home() / '.ctfd_config.json'
        self.session = requests.Session()
        self.base_url = None
        self.token = None
        self.deployed_tasks = {}
        self.failed_tasks = []
        self.file_errors = []
        self.existing_challenges = []
        
    def load_credentials(self) -> bool:
        """Load stored credentials if they exist"""
        if not self.config_file.exists():
            return False
            
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.base_url = config.get('url')
                self.token = config.get('token')
                return bool(self.base_url and self.token)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading config: {e}")
            return False
    
    def save_credentials(self, url: str, token: str):
        """Save credentials for future use"""
        try:
            config = {'url': url, 'token': token}
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"Credentials saved to {self.config_file}")
        except IOError as e:
            print(f"Warning: Could not save credentials: {e}")
    
    def get_credentials(self) -> tuple[str, str]:
        """Get credentials from user or use stored ones"""
        if self.load_credentials():
            print(f"Found stored credentials for: {self.base_url}")
            use_stored = input("Use stored credentials? (y/n): ").lower().strip()
            
            if use_stored in ['y', 'yes', '']:
                return self.base_url, self.token
        
        url = input("Enter CTFd URL (e.g., https://ctf.example.com): ").strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        token = input("Enter admin token: ").strip()
        
        save = input("Save credentials for future use? (y/n): ").lower().strip()
        if save in ['y', 'yes', '']:
            self.save_credentials(url, token)
        
        return url, token 
   
    def setup_session(self, url: str, token: str):
        """Setup session with auth headers"""
        self.base_url = url.rstrip('/')
        self.token = token
        self.session.headers.update({
            'Authorization': f'Token {token}',
            'Content-Type': 'application/json'
        })
    
    def test_connection(self) -> bool:
        """Test if we can connect to CTFd"""
        try:
            response = self.session.get(f"{self.base_url}/api/v1/users/me")
            if response.status_code == 200:
                user_data = response.json()
                print(f"✓ Connected as: {user_data['data']['name']}")
                self.load_existing_challenges()
                return True
            else:
                print(f"✗ Authentication failed: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"✗ Connection failed: {e}")
            return False

    def load_existing_challenges(self):
        """Load existing challenges for duplicate detection"""
        try:
            print(f"🔍 Loading existing challenges from: {self.base_url}/api/v1/challenges?view=admin")
            response = self.session.get(f"{self.base_url}/api/v1/challenges?view=admin")
            print(f"📡 Response status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    print(f"📊 Response structure: {list(response_data.keys())}")
                    
                    if 'data' in response_data:
                        self.existing_challenges = response_data['data']
                    elif isinstance(response_data, list):
                        self.existing_challenges = response_data
                    else:
                        self.existing_challenges = response_data if isinstance(response_data, list) else []
                    
                    print(f"✓ Loaded {len(self.existing_challenges)} existing challenges for duplicate detection")
                    
                    if self.existing_challenges:
                        print("  📋 Existing challenges:")
                        for i, challenge in enumerate(self.existing_challenges[:3]):
                            if isinstance(challenge, dict):
                                print(f"    {i+1}. '{challenge.get('name', 'N/A')}' (ID: {challenge.get('id', 'N/A')})")
                                if i == 0:
                                    print(f"       Sample challenge data: {list(challenge.keys())}")
                            else:
                                print(f"    {i+1}. Unexpected data type: {type(challenge)}")
                        if len(self.existing_challenges) > 3:
                            print(f"    ... and {len(self.existing_challenges) - 3} more")
                    else:
                        print("  📋 No existing challenges found")
                        
                except json.JSONDecodeError as e:
                    print(f"✗ Failed to parse JSON response: {e}")
                    print(f"   Raw response: {response.text[:500]}...")
                    self.existing_challenges = []
            else:
                print(f"⚠️  Could not load existing challenges from either endpoint")
                print(f"    Standard response: {response.status_code}")
                print(f"    Response text: {response.text[:200]}...")
                self.existing_challenges = []
        except Exception as e:
            print(f"⚠️  Error loading existing challenges: {e}")
            import traceback
            print(f"    Traceback: {traceback.format_exc()}")
            self.existing_challenges = []

    def find_duplicate_challenge(self, task_data: Dict, debug: bool = False) -> Optional[Dict]:
        """Check if a challenge with the same name already exists"""
        challenge_name = task_data.get('name', '').strip()
        
        if debug:
            print(f"  🔍 Checking for duplicates of: '{challenge_name}'")
            print(f"  📊 Comparing against {len(self.existing_challenges)} existing challenges")
        
        for existing in self.existing_challenges:
            existing_name = existing.get('name', '').strip()
            if debug:
                print(f"    - Comparing with: '{existing_name}'")
            if existing_name == challenge_name:
                if debug:
                    print(f"    ✓ Found duplicate: '{existing_name}' (ID: {existing.get('id')})")
                return existing
        
        if debug:
            print(f"    ✓ No duplicates found for: '{challenge_name}'")
        return None

    def is_identical_challenge(self, task_data: Dict, existing_challenge: Dict) -> bool:
        """Compare key fields to see if challenges are identical"""
        fields_to_compare = ['name', 'description', 'category', 'value', 'type', 'state']
        
        for field in fields_to_compare:
            new_value = str(task_data.get(field, '')).strip()
            existing_value = str(existing_challenge.get(field, '')).strip()
            if new_value != existing_value:
                return False
        
        return True

    def handle_duplicate_challenge(self, task_data: Dict, existing_challenge: Dict) -> str:
        """Handle duplicate challenge with user interaction."""
        challenge_name = task_data.get('name', 'Unnamed Challenge')
        
        print(f"\n⚠️  DUPLICATE CHALLENGE DETECTED")
        print(f"   Challenge: {challenge_name}")
        print(f"   Existing ID: {existing_challenge['id']}")
        
        # Check if they're identical
        if self.is_identical_challenge(task_data, existing_challenge):
            print(f"   Status: IDENTICAL - No changes detected")
            print(f"   Category: {existing_challenge.get('category', 'N/A')}")
            print(f"   Value: {existing_challenge.get('value', 'N/A')} points")
            
            while True:
                choice = input("   Action: (s)kip, (a)dd anyway, (q)uit: ").lower().strip()
                
                if choice in ['s', 'skip']:
                    print(f"   ✓ Skipped identical challenge: {challenge_name}")
                    return 'skip'
                elif choice in ['a', 'add']:
                    print(f"   ⚠️  Adding duplicate challenge: {challenge_name}")
                    return 'add'
                elif choice in ['q', 'quit']:
                    print("   Deployment cancelled by user")
                    sys.exit(1)
                else:
                    print("   Invalid choice. Please enter 's' for skip, 'a' for add anyway, or 'q' to quit")
        else:
            print(f"   Status: DIFFERENT - Changes detected, will deploy")
            print(f"   Existing - Category: {existing_challenge.get('category', 'N/A')}, Value: {existing_challenge.get('value', 'N/A')}")
            print(f"   New      - Category: {task_data.get('category', 'N/A')}, Value: {task_data.get('value', 'N/A')}")
            return 'add'
    
    def find_task_files(self, directory: Path) -> List[Path]:
        """Find challenge.yml or challenge.json files in directory and subdirectories"""
        task_files = []
        challenge_files = ['challenge.yml', 'challenge.yaml', 'challenge.json']
        
        for filename in challenge_files:
            file_path = directory / filename
            if file_path.exists():
                task_files.append(file_path)
                return task_files
        
        try:
            for item in directory.iterdir():
                if item.is_dir():
                    for filename in challenge_files:
                        file_path = item / filename
                        if file_path.exists():
                            task_files.append(file_path)
                            break
        except PermissionError:
            print(f"✗ Permission denied accessing directory: {directory}")
            return []
        
        return sorted(task_files)
    
    def load_task_config(self, task_file: Path) -> Optional[Dict]:
        """Load challenge config from YAML or JSON"""
        try:
            with open(task_file, 'r', encoding='utf-8') as f:
                if task_file.suffix.lower() in ['.yml', '.yaml']:
                    return yaml.safe_load(f)
                else:
                    return json.load(f)
        except (yaml.YAMLError, json.JSONDecodeError, IOError) as e:
            print(f"✗ Error loading {task_file}: {e}")
            return None    

    def create_challenge(self, task_data: Dict, task_dir: Path, force_duplicates: bool = False, debug_duplicates: bool = False) -> bool:
        """Create a challenge in CTFd."""
        challenge_name = task_data.get('name', 'Unnamed Challenge')
        category = task_data.get('category', 'misc')
        
        # Check for duplicates (unless forced to skip)
        if not force_duplicates:
            existing_challenge = self.find_duplicate_challenge(task_data, debug_duplicates)
            if existing_challenge:
                action = self.handle_duplicate_challenge(task_data, existing_challenge)
                if action == 'skip':
                    # Track as skipped, not failed
                    if category not in self.deployed_tasks:
                        self.deployed_tasks[category] = []
                    self.deployed_tasks[category].append({
                        'name': challenge_name,
                        'id': existing_challenge['id'],
                        'value': existing_challenge.get('value', 0),
                        'type': existing_challenge.get('type', 'standard'),
                        'state': existing_challenge.get('state', 'visible'),
                        'status': 'skipped_duplicate'
                    })
                    return True  # Consider this a success since user chose to skip
        
        try:
            # Prepare challenge data
            challenge_data = {
                'name': challenge_name,
                'description': task_data.get('description', ''),
                'value': task_data.get('value', 100),
                'category': category,
                'type': task_data.get('type', 'standard'),
                'state': task_data.get('state', 'visible')
            }
            
            # Handle dynamic challenges
            if challenge_data['type'] == 'dynamic' and 'extra' in task_data:
                extra = task_data['extra']
                challenge_data.update({
                    'initial': extra.get('initial', challenge_data['value']),
                    'decay': extra.get('decay', 20),
                    'minimum': extra.get('minimum', 100)
                })
            
            # Create the challenge
            response = self.session.post(
                f"{self.base_url}/api/v1/challenges",
                json=challenge_data
            )
            
            if response.status_code != 200:
                error_msg = f"Failed to create challenge '{challenge_name}': {response.text}"
                print(f"✗ {error_msg}")
                self.failed_tasks.append({
                    'name': challenge_name,
                    'category': category,
                    'error': error_msg,
                    'stage': 'creation'
                })
                return False
            
            challenge_id = response.json()['data']['id']
            print(f"✓ Created challenge '{challenge_name}' (ID: {challenge_id})")
            
            # Track successful creation
            if category not in self.deployed_tasks:
                self.deployed_tasks[category] = []
            
            task_info = {
                'name': challenge_name,
                'id': challenge_id,
                'value': challenge_data['value'],
                'type': challenge_data['type'],
                'state': challenge_data['state']
            }
            
            # Add flags
            if 'flags' in task_data:
                if not self.add_flags(challenge_id, task_data['flags']):
                    task_info['flags_error'] = True
            
            # Add hints
            if 'hints' in task_data:
                if not self.add_hints(challenge_id, task_data['hints']):
                    task_info['hints_error'] = True
            
            # Upload files
            if 'files' in task_data:
                if not self.upload_files(challenge_id, task_data['files'], task_dir, challenge_name):
                    task_info['files_error'] = True
            
            self.deployed_tasks[category].append(task_info)
            return True
            
        except Exception as e:
            error_msg = f"Error creating challenge: {e}"
            print(f"✗ {error_msg}")
            self.failed_tasks.append({
                'name': challenge_name,
                'category': category,
                'error': error_msg,
                'stage': 'creation'
            })
            return False
    
    def add_flags(self, challenge_id: int, flags: List) -> bool:
        """Add flags to a challenge"""
        try:
            for flag_data in flags:
                if isinstance(flag_data, str):
                    flag_data = {'content': flag_data, 'type': 'static'}
                
                response = self.session.post(
                    f"{self.base_url}/api/v1/flags",
                    json={
                        'challenge_id': challenge_id,
                        'content': flag_data['content'],
                        'type': flag_data.get('type', 'static')
                    }
                )
                
                if response.status_code == 200:
                    print(f"  ✓ Added flag: {flag_data['content']}")
                else:
                    print(f"  ✗ Failed to add flag: {response.text}")
                    return False
            return True
        except Exception as e:
            print(f"✗ Error adding flags: {e}")
            return False    

    def add_hints(self, challenge_id: int, hints: List) -> bool:
        """Add hints to a challenge"""
        try:
            for hint_data in hints:
                if isinstance(hint_data, str):
                    hint_data = {'content': hint_data, 'cost': 0}
                
                response = self.session.post(
                    f"{self.base_url}/api/v1/hints",
                    json={
                        'challenge_id': challenge_id,
                        'content': hint_data['content'],
                        'cost': hint_data.get('cost', 0)
                    }
                )
                
                if response.status_code == 200:
                    print(f"  ✓ Added hint (cost: {hint_data.get('cost', 0)})")
                else:
                    print(f"  ✗ Failed to add hint: {response.text}")
                    return False
            return True
        except Exception as e:
            print(f"✗ Error adding hints: {e}")
            return False
    
    def handle_missing_file(self, file_path: str, task_dir: Path, challenge_name: str) -> Optional[Path]:
        """Handle missing file with user interaction."""
        print(f"\n  ⚠️  File not found: {file_path}")
        print(f"     Challenge: {challenge_name}")
        print(f"     Expected location: {task_dir / file_path}")
        
        while True:
            choice = input("  Choose action: (s)kip, (p)ath to file, (q)uit deployment: ").lower().strip()
            
            if choice in ['s', 'skip']:
                self.file_errors.append({
                    'challenge': challenge_name,
                    'file': file_path,
                    'action': 'skipped',
                    'reason': 'File not found - user chose to skip'
                })
                return None
            
            elif choice in ['p', 'path']:
                new_path = input("  Enter full path to file: ").strip().strip('"').strip("'")
                if new_path:
                    new_file_path = Path(new_path)
                    if new_file_path.exists():
                        print(f"  ✓ Found file at: {new_file_path}")
                        return new_file_path
                    else:
                        print(f"  ✗ File still not found: {new_file_path}")
                        continue
                else:
                    print("  ✗ No path provided")
                    continue
            
            elif choice in ['q', 'quit']:
                print("  Deployment cancelled by user")
                sys.exit(1)
            
            else:
                print("  Invalid choice. Please enter 's' for skip, 'p' for path, or 'q' to quit")

    def upload_files(self, challenge_id: int, files: List, task_dir: Path, challenge_name: str = "Unknown") -> bool:
        """Upload challenge files"""
        try:
            for file_path in files:
                full_path = task_dir / file_path
                if not full_path.exists():
                    alternative_path = self.handle_missing_file(file_path, task_dir, challenge_name)
                    if alternative_path is None:
                        continue
                    full_path = alternative_path
                
                with open(full_path, 'rb') as f:
                    files_data = {'file': (full_path.name, f, 'application/octet-stream')}
                    
                    headers = self.session.headers.copy()
                    if 'Content-Type' in self.session.headers:
                        del self.session.headers['Content-Type']
                    
                    response = self.session.post(
                        f"{self.base_url}/api/v1/files",
                        files=files_data,
                        data={'challenge_id': challenge_id}
                    )
                    
                    self.session.headers.update(headers)
                
                if response.status_code == 200:
                    print(f"  ✓ Uploaded file: {file_path}")
                else:
                    print(f"  ✗ Failed to upload {file_path}: {response.text}")
                    return False
            return True
        except Exception as e:
            print(f"✗ Error uploading files: {e}")
            return False 
   
    def deploy_tasks(self, directory: Path, force_duplicates: bool = False, debug_duplicates: bool = False) -> bool:
        """Deploy all tasks from directory."""
        # Resolve the path to handle relative paths properly
        directory = directory.resolve()
        
        if not directory.exists():
            print(f"✗ Directory not found: {directory}")
            print(f"Current working directory: {Path.cwd()}")
            return False
        
        task_files = self.find_task_files(directory)
        if not task_files:
            print(f"✗ No challenge files found in {directory}")
            print("Looking for: challenge.yml or challenge.yaml files in subdirectories")
            return False
        
        print(f"Found {len(task_files)} task file(s)")
        
        success_count = 0
        for task_file in task_files:
            print(f"\nProcessing: {task_file}")
            
            task_data = self.load_task_config(task_file)
            if not task_data:
                continue
            
            task_dir = task_file.parent
            if self.create_challenge(task_data, task_dir, force_duplicates, debug_duplicates):
                success_count += 1
        
        print(f"\n{'='*50}")
        print(f"Deployment complete: {success_count}/{len(task_files)} tasks deployed successfully")
        
        # Show deployment summary
        self.show_deployment_summary()
        
        return success_count > 0

    def show_deployment_summary(self):
        """Display deployment summary by category and errors."""
        print(f"\n{'='*60}")
        print("DEPLOYMENT SUMMARY")
        print(f"{'='*60}")
        
        # Show deployed tasks by category
        if self.deployed_tasks:
            print("\n✓ SUCCESSFULLY DEPLOYED TASKS:")
            for category, tasks in sorted(self.deployed_tasks.items()):
                print(f"\n  📁 {category.upper()} ({len(tasks)} tasks)")
                for task in tasks:
                    status_icons = []
                    if task.get('status') == 'skipped_duplicate':
                        status_icons.append("⏭️ skipped duplicate")
                    if task.get('flags_error'):
                        status_icons.append("⚠️ flags")
                    if task.get('hints_error'):
                        status_icons.append("⚠️ hints")
                    if task.get('files_error'):
                        status_icons.append("⚠️ files")
                    
                    status_str = f" [{', '.join(status_icons)}]" if status_icons else ""
                    print(f"    • {task['name']} (ID: {task['id']}, {task['value']} pts){status_str}")
        
        # Show failed tasks
        if self.failed_tasks:
            print(f"\n✗ FAILED TASKS ({len(self.failed_tasks)}):")
            for task in self.failed_tasks:
                print(f"  • {task['name']} ({task['category']})")
                print(f"    Error: {task['error']}")
                print(f"    Stage: {task['stage']}")
        
        # Show file errors
        if self.file_errors:
            print(f"\n⚠️  FILE ISSUES ({len(self.file_errors)}):")
            for error in self.file_errors:
                print(f"  • {error['challenge']}: {error['file']}")
                print(f"    Action: {error['action']} - {error['reason']}")
        
        # Summary stats
        total_deployed = 0
        total_skipped = 0
        for tasks in self.deployed_tasks.values():
            for task in tasks:
                if task.get('status') == 'skipped_duplicate':
                    total_skipped += 1
                else:
                    total_deployed += 1
        
        total_failed = len(self.failed_tasks)
        total_file_issues = len(self.file_errors)
        
        print(f"\n{'='*60}")
        print(f"STATISTICS:")
        print(f"  ✓ Successfully deployed: {total_deployed}")
        print(f"  ⏭️  Skipped duplicates: {total_skipped}")
        print(f"  ✗ Failed: {total_failed}")
        print(f"  ⚠️  File issues: {total_file_issues}")
        print(f"  📊 Categories: {len(self.deployed_tasks)}")
        print(f"{'='*60}")

    def list_deployed_challenges(self):
        """List all currently deployed challenges by category."""
        try:
            print(f"🔍 Fetching challenges from: {self.base_url}/api/v1/challenges?view=admin")
            response = self.session.get(f"{self.base_url}/api/v1/challenges?view=admin")
            
            print(f"📡 Response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"✗ Failed to fetch challenges from API endpoint")
                print(f"   Response: {response.text[:200]}...")
                print(f"   Make sure your admin token has the correct permissions")
                return
            
            try:
                response_data = response.json()
                print(f"📊 Response structure: {list(response_data.keys())}")
                
                # Handle different response formats
                if 'data' in response_data:
                    challenges = response_data['data']
                elif isinstance(response_data, list):
                    challenges = response_data
                else:
                    challenges = response_data
                    
                print(f"📋 Found {len(challenges)} challenges in response")
                
            except json.JSONDecodeError as e:
                print(f"✗ Failed to parse JSON response: {e}")
                print(f"   Raw response: {response.text[:500]}...")
                return
            
            if not challenges:
                print("No challenges found on the CTFd instance.")
                return
            
            # Group by category
            by_category = {}
            for challenge in challenges:
                category = challenge.get('category', 'uncategorized')
                if category not in by_category:
                    by_category[category] = []
                by_category[category].append(challenge)
            
            print(f"\n{'='*60}")
            print("CURRENTLY DEPLOYED CHALLENGES")
            print(f"{'='*60}")
            
            total_challenges = 0
            for category, challs in sorted(by_category.items()):
                print(f"\n📁 {category.upper()} ({len(challs)} challenges)")
                total_challenges += len(challs)
                
                for chall in sorted(challs, key=lambda x: x['name']):
                    state_icon = "👁️" if chall.get('state') == 'visible' else "🔒"
                    type_info = f"[{chall.get('type', 'standard')}]" if chall.get('type') != 'standard' else ""
                    print(f"  {state_icon} {chall['name']} (ID: {chall['id']}, {chall.get('value', 0)} pts) {type_info}")
            
            print(f"\n{'='*60}")
            print(f"Total: {total_challenges} challenges across {len(by_category)} categories")
            print(f"{'='*60}")
            
        except Exception as e:
            print(f"✗ Error fetching challenges: {e}")


    def offline_preview_tasks(self, directory: Path):
        """Preview local tasks without connecting to CTFd."""
        print(f"\n{'='*80}")
        print("LOCAL TASKS PREVIEW (OFFLINE MODE)")
        print(f"{'='*80}")
        
        print(f"\n🔍 Scanning directory: {directory}")
        task_files = self.find_task_files(directory)
        
        if not task_files:
            print("📁 No challenge files found")
            print("Expected structure:")
            print("  - Single challenge: challenge.yml in the specified directory")
            print("  - Multiple challenges: each challenge in its own subdirectory with challenge.yml")
            return
        
        print(f"📁 Found {len(task_files)} task file(s)")
        
        tasks_by_category = {}
        total_points = 0
        
        for task_file in task_files:
            print(f"\n📄 Processing: {task_file}")
            task_data = self.load_task_config(task_file)
            
            if not task_data:
                print(f"  ❌ Failed to load configuration")
                continue
            
            category = task_data.get('category', 'misc')
            task_name = task_data.get('name', 'Unnamed')
            value = task_data.get('value', 100)
            
            if category not in tasks_by_category:
                tasks_by_category[category] = []
            
            task_info = {
                'name': task_name,
                'file': task_file,
                'value': value,
                'type': task_data.get('type', 'standard'),
                'state': task_data.get('state', 'visible'),
                'flags': task_data.get('flags', []),
                'hints': task_data.get('hints', []),
                'files': task_data.get('files', []),
                'description': task_data.get('description', '')
            }
            
            tasks_by_category[category].append(task_info)
            total_points += value
            
            # Show task details
            print(f"  ✅ {task_name}")
            print(f"     Category: {category}")
            print(f"     Value: {value} points")
            print(f"     Type: {task_info['type']}")
            print(f"     State: {task_info['state']}")
            print(f"     Flags: {len(task_info['flags'])}")
            print(f"     Hints: {len(task_info['hints'])}")
            print(f"     Files: {len(task_info['files'])}")
            
            # Check if files exist
            if task_info['files']:
                print(f"     File status:")
                for file_path in task_info['files']:
                    full_path = task_file.parent / file_path
                    status = "✅" if full_path.exists() else "❌"
                    print(f"       {status} {file_path}")
        
        # Summary by category
        print(f"\n{'='*80}")
        print("SUMMARY BY CATEGORY")
        print(f"{'='*80}")
        
        for category, tasks in sorted(tasks_by_category.items()):
            category_points = sum(task['value'] for task in tasks)
            print(f"\n📂 {category.upper()} ({len(tasks)} tasks, {category_points} total points)")
            
            for task in sorted(tasks, key=lambda x: x['name']):
                state_icon = "👁️" if task['state'] == 'visible' else "🔒"
                type_info = f"[{task['type']}]" if task['type'] != 'standard' else ""
                print(f"  {state_icon} {task['name']} ({task['value']} pts) {type_info}")
        
        print(f"\n{'='*80}")
        print(f"TOTAL: {len(task_files)} tasks, {total_points} points across {len(tasks_by_category)} categories")
        print(f"{'='*80}")
        
        print(f"\n💡 Next steps:")
        print(f"   • Use --dry-run to see deployment simulation")
        print(f"   • Use --preview to compare with deployed tasks (requires CTFd connection)")
        print(f"   • Run without flags to deploy to CTFd")

    def preview_tasks_comparison(self, directory: Path):
        """Preview and compare local tasks with deployed tasks."""
        print(f"\n{'='*80}")
        print("TASK PREVIEW & COMPARISON")
        print(f"{'='*80}")
        
        # Get local tasks
        print(f"\n🔍 Scanning local directory: {directory}")
        task_files = self.find_task_files(directory)
        
        local_tasks = {}  # category -> list of tasks
        local_task_names = set()
        
        if task_files:
            print(f"📁 Found {len(task_files)} local task file(s)")
            
            for task_file in task_files:
                task_data = self.load_task_config(task_file)
                if task_data:
                    category = task_data.get('category', 'misc')
                    task_name = task_data.get('name', 'Unnamed')
                    
                    if category not in local_tasks:
                        local_tasks[category] = []
                    
                    local_tasks[category].append({
                        'name': task_name,
                        'file': task_file,
                        'value': task_data.get('value', 100),
                        'type': task_data.get('type', 'standard'),
                        'state': task_data.get('state', 'visible'),
                        'flags': len(task_data.get('flags', [])),
                        'hints': len(task_data.get('hints', [])),
                        'files': len(task_data.get('files', [])),
                        'data': task_data
                    })
                    local_task_names.add(task_name)
        else:
            print("📁 No local task files found")
        
        # Get deployed tasks
        print(f"\n🌐 Fetching deployed tasks from CTFd...")
        deployed_tasks = {}  # category -> list of tasks
        deployed_task_names = set()
        
        try:
            response = self.session.get(f"{self.base_url}/api/v1/challenges?view=admin")
            
            if response.status_code == 200:
                response_data = response.json()
                challenges = response_data.get('data', response_data)
                
                if challenges:
                    print(f"🌐 Found {len(challenges)} deployed challenge(s)")
                    
                    for challenge in challenges:
                        category = challenge.get('category', 'misc')
                        task_name = challenge.get('name', 'Unnamed')
                        
                        if category not in deployed_tasks:
                            deployed_tasks[category] = []
                        
                        deployed_tasks[category].append({
                            'name': task_name,
                            'id': challenge.get('id'),
                            'value': challenge.get('value', 0),
                            'type': challenge.get('type', 'standard'),
                            'state': challenge.get('state', 'visible')
                        })
                        deployed_task_names.add(task_name)
                else:
                    print("🌐 No deployed challenges found")
            else:
                print(f"❌ Failed to fetch deployed challenges: {response.status_code}")
        except Exception as e:
            print(f"❌ Error fetching deployed challenges: {e}")
        
        # Show comparison
        print(f"\n{'='*80}")
        print("COMPARISON RESULTS")
        print(f"{'='*80}")
        
        all_categories = set(local_tasks.keys()) | set(deployed_tasks.keys())
        
        if not all_categories:
            print("No tasks found locally or on CTFd")
            return
        
        for category in sorted(all_categories):
            print(f"\n📂 Category: {category.upper()}")
            print("-" * 60)
            
            local_cat_tasks = local_tasks.get(category, [])
            deployed_cat_tasks = deployed_tasks.get(category, [])
            
            local_names = {task['name'] for task in local_cat_tasks}
            deployed_names = {task['name'] for task in deployed_cat_tasks}
            
            # Tasks in both local and deployed
            common_names = local_names & deployed_names
            if common_names:
                print("🔄 Tasks in BOTH local and deployed:")
                for name in sorted(common_names):
                    local_task = next(t for t in local_cat_tasks if t['name'] == name)
                    deployed_task = next(t for t in deployed_cat_tasks if t['name'] == name)
                    
                    # Check if they're different
                    differences = []
                    if local_task['value'] != deployed_task['value']:
                        differences.append(f"value: {deployed_task['value']} → {local_task['value']}")
                    if local_task['type'] != deployed_task['type']:
                        differences.append(f"type: {deployed_task['type']} → {local_task['type']}")
                    if local_task['state'] != deployed_task['state']:
                        differences.append(f"state: {deployed_task['state']} → {local_task['state']}")
                    
                    status = "🔄 DIFFERENT" if differences else "✅ IDENTICAL"
                    print(f"  {status} {name} (ID: {deployed_task['id']})")
                    if differences:
                        print(f"    Changes: {', '.join(differences)}")
            
            # Tasks only in local
            local_only = local_names - deployed_names
            if local_only:
                print("📤 Tasks ONLY in local (will be deployed):")
                for name in sorted(local_only):
                    local_task = next(t for t in local_cat_tasks if t['name'] == name)
                    print(f"  ➕ NEW {name} ({local_task['value']} pts, {local_task['type']})")
            
            # Tasks only in deployed
            deployed_only = deployed_names - local_names
            if deployed_only:
                print("📥 Tasks ONLY in deployed (not in local):")
                for name in sorted(deployed_only):
                    deployed_task = next(t for t in deployed_cat_tasks if t['name'] == name)
                    print(f"  🌐 DEPLOYED {name} (ID: {deployed_task['id']}, {deployed_task['value']} pts)")
        
        # Summary
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")
        print(f"📁 Local tasks: {len(local_task_names)}")
        print(f"🌐 Deployed tasks: {len(deployed_task_names)}")
        print(f"🔄 Common tasks: {len(local_task_names & deployed_task_names)}")
        print(f"📤 New tasks (local only): {len(local_task_names - deployed_task_names)}")
        print(f"📥 Deployed only: {len(deployed_task_names - local_task_names)}")
        
        if local_task_names - deployed_task_names:
            print(f"\n➡️  Run without --preview to deploy {len(local_task_names - deployed_task_names)} new task(s)")
        elif local_task_names & deployed_task_names:
            print(f"\n➡️  Run with --force-duplicates to update existing tasks")
        
        print(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(
        description='Deploy CTF tasks to CTFd instance with preview and management capabilities',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Deploy from current directory
  %(prog)s ./challenges                 # Deploy from specific directory
  %(prog)s --preview ./challenges       # Preview local vs deployed tasks
  %(prog)s --list-deployed              # List current challenges on CTFd
  %(prog)s --dry-run ./challenges       # Show what would be deployed
  %(prog)s --force-duplicates ./tasks   # Skip duplicate detection
        """
    )
    parser.add_argument('directory', nargs='?', default='.', 
                       help='Directory containing challenge subdirectories (default: current directory)')
    parser.add_argument('--url', help='CTFd URL (overrides stored config)')
    parser.add_argument('--token', help='Admin token (overrides stored config)')
    parser.add_argument('--preview', action='store_true', 
                       help='Compare local tasks with deployed tasks (recommended first step)')
    parser.add_argument('--list-deployed', action='store_true', 
                       help='List currently deployed challenges by category')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be deployed without actually doing it')
    parser.add_argument('--force-duplicates', action='store_true', 
                       help='Skip duplicate detection and add all challenges')
    parser.add_argument('--debug-duplicates', action='store_true', 
                       help='Show detailed duplicate detection debug info')
    parser.add_argument('--offline-preview', action='store_true',
                       help='Preview local tasks without connecting to CTFd')
    
    args = parser.parse_args()
    
    deployer = CTFdDeployer()
    
    # Handle offline preview first (no connection needed)
    if args.offline_preview:
        try:
            dir_path = args.directory.strip().strip('"').strip("'")
            directory = Path(dir_path).expanduser().resolve()
            deployer.offline_preview_tasks(directory)
            sys.exit(0)
        except Exception as e:
            print(f"✗ Error during offline preview: {e}")
            sys.exit(1)
    
    try:
        # Get credentials
        if args.url and args.token:
            url, token = args.url, args.token
        else:
            url, token = deployer.get_credentials()
        
        # Setup session
        deployer.setup_session(url, token)
        
        # Test connection
        if not deployer.test_connection():
            print("✗ Failed to connect to CTFd. Please check your credentials.")
            sys.exit(1)
        
        # Handle list-deployed option
        if args.list_deployed:
            deployer.list_deployed_challenges()
            sys.exit(0)
        
        # Handle preview option
        if args.preview:
            try:
                dir_path = args.directory.strip().strip('"').strip("'")
                directory = Path(dir_path).expanduser().resolve()
                deployer.preview_tasks_comparison(directory)
                sys.exit(0)
            except Exception as e:
                print(f"✗ Error during preview: {e}")
                sys.exit(1)
        
        # Deploy tasks
        try:
            # Clean up the directory path - remove quotes if present
            dir_path = args.directory.strip().strip('"').strip("'")
            directory = Path(dir_path).expanduser().resolve()
        except Exception as e:
            print(f"✗ Invalid directory path '{args.directory}': {e}")
            sys.exit(1)
            
        print(f"Looking for challenges in: {directory}")
        
        if not directory.exists():
            print(f"✗ Directory does not exist: {directory}")
            print(f"Original argument: '{args.directory}'")
            print(f"Current working directory: {Path.cwd()}")
            sys.exit(1)
            
        if not directory.is_dir():
            print(f"✗ Path is not a directory: {directory}")
            sys.exit(1)
        
        if args.dry_run:
            print("DRY RUN MODE - No changes will be made")
            task_files = deployer.find_task_files(directory)
            if not task_files:
                print(f"✗ No challenge.yml files found in {directory}")
                print("Expected structure:")
                print("  - Single challenge: challenge.yml in the specified directory")
                print("  - Multiple challenges: each challenge in its own subdirectory with challenge.yml")
                print(f"Contents of {directory}:")
                try:
                    for item in directory.iterdir():
                        print(f"  {'[DIR]' if item.is_dir() else '[FILE]'} {item.name}")
                except PermissionError:
                    print("  (Permission denied)")
                sys.exit(1)
            
            for task_file in task_files:
                task_data = deployer.load_task_config(task_file)
                if task_data:
                    print(f"Would deploy: {task_data.get('name', 'Unnamed')} from {task_file.parent.name}/")
        else:
            success = deployer.deploy_tasks(directory, args.force_duplicates, args.debug_duplicates)
            sys.exit(0 if success else 1)
            
    except KeyboardInterrupt:
        print("\n✗ Deployment cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()