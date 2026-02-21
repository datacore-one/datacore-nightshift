"""
Org-mode file parser for nightshift.
Extracts :AI: tagged tasks and manages task properties.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime


@dataclass
class OrgTask:
    """Represents an org-mode task with properties."""
    id: str
    title: str
    state: str  # TODO, NEXT, WORKING, DONE, REVIEW, FAILED
    tags: List[str]
    properties: Dict[str, str]
    file_path: Path
    line_number: int
    heading_level: int
    body: str = ""

    @property
    def ai_tag(self) -> Optional[str]:
        """Get the primary :AI: tag (e.g., :AI:content:, :AI:research:)."""
        for tag in self.tags:
            if tag.startswith('AI'):
                return f":{tag}:"
        return None

    @property
    def space(self) -> Optional[str]:
        """Get the space from SPACE property or file path."""
        if 'SPACE' in self.properties:
            return self.properties['SPACE']
        # Infer from path (e.g., 1-teamspace/org/next_actions.org -> 1-teamspace)
        parts = self.file_path.parts
        for part in parts:
            if re.match(r'^\d+-', part):
                return part
        if '0-personal' in str(self.file_path):
            return '0-personal'
        return None


def parse_org_file(file_path: Path) -> List[OrgTask]:
    """Parse an org file and extract all tasks."""
    tasks = []

    if not file_path.exists():
        return tasks

    content = file_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i]

        # Match heading: * TODO Title :tag1:tag2:
        heading_match = re.match(
            r'^(\*+)\s+(TODO|NEXT|WORKING|DONE|REVIEW|FAILED|WAITING|QUEUED|EXECUTING)\s+(.+?)(\s+:[\w:]+:)?\s*$',
            line
        )

        if heading_match:
            level = len(heading_match.group(1))
            state = heading_match.group(2)
            title = heading_match.group(3).strip()
            tags_str = heading_match.group(4) or ""
            tags = [t for t in tags_str.strip().strip(':').split(':') if t]

            # Parse properties drawer
            properties = {}
            accumulating = None  # Track multiline property accumulation
            body_lines = []
            j = i + 1
            in_properties = False

            while j < len(lines):
                next_line = lines[j]

                # Check for next heading at same or higher level
                if re.match(r'^\*{1,' + str(level) + r'}\s', next_line):
                    break

                # Properties drawer
                if next_line.strip() == ':PROPERTIES:':
                    in_properties = True
                    j += 1
                    continue
                elif next_line.strip() == ':END:':
                    in_properties = False
                    j += 1
                    continue

                if in_properties:
                    prop_match = re.match(r'^:(\w+):\s*(.*)$', next_line.strip())
                    if prop_match:
                        current_prop = prop_match.group(1)
                        current_val = prop_match.group(2)
                        if current_val.strip() == '|':
                            # Multiline property — accumulate continuation lines
                            properties[current_prop] = ''
                            accumulating = current_prop
                        else:
                            properties[current_prop] = current_val
                            accumulating = None
                    elif accumulating:
                        # Continuation line for multiline property
                        properties[accumulating] += next_line.rstrip() + '\n'
                    # else: non-property, non-continuation line inside drawer — skip
                else:
                    body_lines.append(next_line)

                j += 1

            # Generate task ID
            task_id = properties.get('ID') or f"{file_path.stem}-L{i+1}"

            task = OrgTask(
                id=task_id,
                title=title,
                state=state,
                tags=tags,
                properties=properties,
                file_path=file_path,
                line_number=i + 1,
                heading_level=level,
                body='\n'.join(body_lines).strip()
            )
            tasks.append(task)

        i += 1

    return tasks


def find_ai_tasks(
    data_dir: Path,
    states: List[str] = None,
    spaces: List[str] = None,
    exclude_spaces: List[str] = None
) -> List[OrgTask]:
    """Find all :AI: tagged tasks in the data directory.

    Args:
        data_dir: Root data directory
        states: Task states to include (default: TODO, NEXT)
        spaces: Only include tasks from these spaces (default: all)
        exclude_spaces: Exclude tasks from these spaces (default: none)
    """
    if states is None:
        states = ['TODO', 'NEXT']

    ai_tasks = []

    # Search in all org files
    for org_file in data_dir.rglob('*.org'):
        # Skip directories that happen to match *.org (e.g., golang.org)
        if not org_file.is_file():
            continue

        # Skip archive files
        if 'archive' in str(org_file).lower():
            continue

        # Check space filtering
        file_path_str = str(org_file)

        # If spaces specified, only include matching spaces
        if spaces:
            if not any(f"/{space}/" in file_path_str or file_path_str.startswith(f"{space}/") for space in spaces):
                continue

        # If exclude_spaces specified, skip matching spaces
        if exclude_spaces:
            if any(f"/{space}/" in file_path_str or f"/{space}" in file_path_str for space in exclude_spaces):
                continue

        tasks = parse_org_file(org_file)
        for task in tasks:
            # Check if task has :AI: tag and is in desired state
            if any(tag.startswith('AI') for tag in task.tags):
                if task.state in states:
                    ai_tasks.append(task)

    return ai_tasks


def update_task_property(task: OrgTask, prop_name: str, prop_value: str) -> str:
    """Update a property in an org file. Returns the modified file content."""
    content = task.file_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    # Find the task heading line
    heading_line_idx = task.line_number - 1

    # Find or create properties drawer
    properties_start = None
    properties_end = None

    # Look for existing properties drawer after the heading
    for i in range(heading_line_idx + 1, min(heading_line_idx + 20, len(lines))):
        line = lines[i].strip()
        if line == ':PROPERTIES:':
            properties_start = i
        elif line == ':END:' and properties_start is not None:
            properties_end = i
            break
        elif re.match(r'^\*+\s', lines[i]):
            # Hit next heading, no properties drawer
            break

    # Format the property value (single-line or multiline)
    if '\n' in prop_value:
        # Multiline: write with | continuation
        formatted_lines = [f':{prop_name}: |']
        for line in prop_value.split('\n'):
            formatted_lines.append(f'  {line}')
    else:
        formatted_lines = [f':{prop_name}: {prop_value}']

    if properties_start is not None and properties_end is not None:
        # Check if property already exists (may span multiple lines if multiline)
        prop_line_idx = None
        prop_end_idx = None
        for i in range(properties_start + 1, properties_end):
            if lines[i].strip().startswith(f':{prop_name}:'):
                prop_line_idx = i
                # Check if it's a multiline property (value is exactly "|")
                val_match = re.match(r'^:(\w+):\s*(.*)$', lines[i].strip())
                if val_match and val_match.group(2).strip() == '|':
                    # Find end of continuation lines
                    prop_end_idx = i + 1
                    while prop_end_idx < properties_end:
                        next_stripped = lines[prop_end_idx].strip()
                        if re.match(r'^:(\w+):\s*(.*)$', next_stripped) or next_stripped == ':END:':
                            break
                        prop_end_idx += 1
                else:
                    prop_end_idx = i + 1
                break

        if prop_line_idx is not None:
            # Replace existing property (single or multiline)
            lines[prop_line_idx:prop_end_idx] = formatted_lines
        else:
            # Add new property before :END:
            for j, new_line in enumerate(formatted_lines):
                lines.insert(properties_end + j, new_line)
    else:
        # Create new properties drawer
        new_lines = [':PROPERTIES:'] + formatted_lines + [':END:']
        insert_idx = heading_line_idx + 1
        for j, new_line in enumerate(new_lines):
            lines.insert(insert_idx + j, new_line)

    return '\n'.join(lines)


def update_task_state(task: OrgTask, new_state: str) -> str:
    """Update the TODO state of a task. Returns the modified file content."""
    content = task.file_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    heading_line_idx = task.line_number - 1
    line = lines[heading_line_idx]

    # Replace the state
    new_line = re.sub(
        r'^(\*+\s+)(TODO|NEXT|WORKING|DONE|REVIEW|FAILED|WAITING|QUEUED|EXECUTING)(\s+)',
        rf'\g<1>{new_state}\3',
        line
    )
    lines[heading_line_idx] = new_line

    return '\n'.join(lines)


def write_org_file(file_path: Path, content: str) -> None:
    """Write content to an org file."""
    file_path.write_text(content, encoding='utf-8')


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python org_parser.py <data_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    tasks = find_ai_tasks(data_dir)

    print(f"Found {len(tasks)} :AI: tasks:")
    for task in tasks:
        print(f"  [{task.state}] {task.title} ({task.ai_tag}) - {task.file_path.name}:{task.line_number}")
