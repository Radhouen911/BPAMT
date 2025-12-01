# Baby Push all my tasks

A Python script for deploying CTF tasks to CTFd instances with credential management and robust error handling.

**Developed by Angel911**

## Features

- **Credential Management**: Stores CTFd URL and admin token locally for reuse
- **Error Handling**: Comprehensive error handling with clear feedback
- **Multiple File Formats**: Supports YAML and JSON task configurations
- **File Upload**: Automatically uploads challenge files
- **Dry Run Mode**: Preview what will be deployed without making changes
- **Progress Tracking**: Clear feedback on deployment progress
- **Interactive File Handling**: Prompts for missing files with options to skip or specify alternative paths
- **Deployment Summary**: Shows deployed tasks by category and tracks errors
- **Challenge Listing**: View currently deployed challenges organized by category
- **Duplicate Detection**: Automatically detects duplicate challenges and prompts for action
- **Smart Comparison**: Distinguishes between identical and modified challenges

## Installation

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

2. Make the script executable (Linux/Mac):

```bash
chmod +x BABY-PUSH-ALL-MYTASKS.py
```

## Usage

### Basic Usage

```bash
python BABY-PUSH-ALL-MYTASKS.py /path/to/challenges/directory
```

Or deploy from current directory:

```bash
python BABY-PUSH-ALL-MYTASKS.py
```

### Command Line Options

```bash
python BABY-PUSH-ALL-MYTASKS.py [OPTIONS] [DIRECTORY]

Arguments:
  DIRECTORY        Directory containing challenge subdirectories (default: current directory)

Options:
  --url URL        CTFd URL (overrides stored config)
  --token TOKEN    Admin token (overrides stored config)
  --dry-run        Show what would be deployed without actually doing it
  --list-deployed  List currently deployed challenges by category
  --force-duplicates Skip duplicate detection and add all challenges
  -h, --help       Show help message
```

### Examples

Deploy challenges from current directory:

```bash
python BABY-PUSH-ALL-MYTASKS.py
```

Deploy challenges from a specific directory:

```bash
python BABY-PUSH-ALL-MYTASKS.py ./ctf_challenges
```

Use specific credentials:

```bash
python BABY-PUSH-ALL-MYTASKS.py --url https://ctf.example.com --token your_admin_token ./challenges
```

Preview deployment without making changes:

```bash
python BABY-PUSH-ALL-MYTASKS.py --dry-run ./challenges
```

List currently deployed challenges:

```bash
python BABY-PUSH-ALL-MYTASKS.py --list-deployed
```

Force deployment without duplicate checking:

```bash
python BABY-PUSH-ALL-MYTASKS.py --force-duplicates ./challenges
```

## Task Configuration Format

Tasks can be defined in YAML or JSON format.

### Required Fields

- `name`: Challenge name
- `description`: Challenge description

### Optional Fields

- `category`: Challenge category (default: "misc")
- `type`: Challenge type (default: "standard")
- `value`: Point value (default: 100)
- `state`: Challenge state - "visible" or "hidden" (default: "visible")
- `flags`: List of flags (can be strings or objects with content/type)
- `hints`: List of hints (can be strings or objects with content/cost)
- `files`: List of file paths relative to the task configuration file

## Directory Structure

The script looks for `challenge.yml` or `challenge.yaml` files in the specified directory and its subdirectories. Each challenge should be in its own subdirectory with a challenge configuration file. Files referenced in the task configuration should be relative to the configuration file location.

Example structure:

```
tasks/
├── web_challenge/
│   ├── challenge.yml
│   ├── challenge.zip
│   └── source.html
├── crypto_challenge/
│   ├── challenge.yml
│   └── encrypted_file.txt
└── misc_challenge/
    └── challenge.yml
```

## Credential Storage

The script stores credentials in `~/.ctfd_config.json`. On first run or when credentials change, you'll be prompted to enter:

- CTFd URL (e.g., https://ctf.example.com)
- Admin token

The script will ask if you want to reuse stored credentials on subsequent runs.

## Error Handling

The script includes comprehensive error handling for:

- Network connectivity issues
- Authentication failures
- Invalid task configurations
- Missing files
- API errors

All errors are reported with clear, actionable messages.

## Security Notes

- Admin tokens are stored in plain text in the config file
- Ensure proper file permissions on the config file
- Use HTTPS URLs for production CTFd instances
- Consider using environment variables for tokens in CI/CD environments
