"""
Nightshift org-mode parser backed by org-workspace library.

Drop-in replacement for org_parser.py.
- Reading: keeps custom parse_org_file for multiline '|' property support
- Writing: uses org-workspace (transition + set_property + save)
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from org_workspace import OrgWorkspace, StateConfig


# ---------------------------------------------------------------------------
# Nightshift state config — all states non-terminal so any transition is valid
# ---------------------------------------------------------------------------

NIGHTSHIFT_STATE_CONFIG = StateConfig(
    sequences={
        'nightshift': [
            'TODO', 'NEXT', 'QUEUED', 'WORKING', 'EXECUTING',
            'WAITING', 'DONE', 'REVIEW', 'FAILED',
        ]
    },
    terminal_states=frozenset(),
)


# ---------------------------------------------------------------------------
# OrgTask dataclass (same interface as org_parser.OrgTask)
# ---------------------------------------------------------------------------

@dataclass
class OrgTask:
    """Represents an org-mode task with properties."""
    id: str
    title: str
    state: str  # TODO, NEXT, WORKING, DONE, REVIEW, FAILED, QUEUED, EXECUTING
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
        parts = self.file_path.parts
        for part in parts:
            if re.match(r'^\d+-', part):
                return part
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_ws(file_path: Path) -> tuple:
    """Load a workspace for a single file. Returns (ws, file_path_resolved)."""
    fp = Path(file_path).resolve()
    ws = OrgWorkspace(state_config=NIGHTSHIFT_STATE_CONFIG)
    if fp.exists():
        ws.load(fp)
    return ws, fp


def _find_node(ws: OrgWorkspace, task: OrgTask):
    """Find the NodeView for a task by its :ID: property."""
    return ws.find_by_id(task.id)


# ---------------------------------------------------------------------------
# parse_org_file — kept from org_parser for multiline '|' property support
# org-workspace puts continuation lines in body, losing the property values.
# ---------------------------------------------------------------------------

def parse_org_file(file_path: Path) -> List[OrgTask]:
    """Parse an org file and extract all tasks (with multiline property support)."""
    tasks = []
    if not file_path.exists():
        return tasks

    content = file_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i]

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

            properties = {}
            accumulating = None
            body_lines = []
            j = i + 1
            in_properties = False

            while j < len(lines):
                next_line = lines[j]

                if re.match(r'^\*{1,' + str(level) + r'}\s', next_line):
                    break

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
                            properties[current_prop] = ''
                            accumulating = current_prop
                        else:
                            properties[current_prop] = current_val
                            accumulating = None
                    elif accumulating:
                        properties[accumulating] += next_line.rstrip() + '\n'
                else:
                    body_lines.append(next_line)

                j += 1

            task_id = properties.get('ID') or f"{file_path.stem}-L{i+1}"

            tasks.append(OrgTask(
                id=task_id,
                title=title,
                state=state,
                tags=tags,
                properties=properties,
                file_path=file_path,
                line_number=i + 1,
                heading_level=level,
                body='\n'.join(body_lines).strip(),
            ))

        i += 1

    return tasks


# ---------------------------------------------------------------------------
# find_ai_tasks — walks data directory, returns :AI: tasks in desired states
# ---------------------------------------------------------------------------

def find_ai_tasks(
    data_dir: Path,
    states: List[str] = None,
    spaces: List[str] = None,
    exclude_spaces: List[str] = None,
) -> List[OrgTask]:
    """Find all :AI: tagged tasks in the data directory."""
    if states is None:
        states = ['TODO', 'NEXT']

    ai_tasks = []

    for org_file in data_dir.rglob('*.org'):
        if not org_file.is_file():
            continue
        if 'archive' in str(org_file).lower():
            continue

        file_path_str = str(org_file)

        if spaces:
            if not any(
                f"/{space}/" in file_path_str or file_path_str.startswith(f"{space}/")
                for space in spaces
            ):
                continue

        if exclude_spaces:
            if any(
                f"/{space}/" in file_path_str or f"/{space}" in file_path_str
                for space in exclude_spaces
            ):
                continue

        for task in parse_org_file(org_file):
            if any(tag.startswith('AI') for tag in task.tags):
                if task.state in states:
                    ai_tasks.append(task)

    return ai_tasks


# ---------------------------------------------------------------------------
# update_task_state — org-workspace backed
# ---------------------------------------------------------------------------

def update_task_state(task: OrgTask, new_state: str) -> str:
    """Update the TODO state of a task via org-workspace. Returns updated file content."""
    ws, fp = _load_ws(task.file_path)
    node = _find_node(ws, task)

    if node is None:
        # Fallback: regex substitution (task has no :ID:)
        content = fp.read_text(encoding='utf-8')
        lines = content.split('\n')
        idx = task.line_number - 1
        if idx < len(lines):
            lines[idx] = re.sub(
                r'^(\*+\s+)(TODO|NEXT|WORKING|DONE|REVIEW|FAILED|WAITING|QUEUED|EXECUTING)(\s+)',
                rf'\g<1>{new_state}\3',
                lines[idx],
            )
        return '\n'.join(lines)

    ws.transition(node, new_state)
    ws.save(fp)
    return fp.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# update_task_property — org-workspace backed
# ---------------------------------------------------------------------------

def update_task_property(task: OrgTask, prop_name: str, prop_value: str) -> str:
    """Update a property in an org file via org-workspace. Returns updated file content."""
    ws, fp = _load_ws(task.file_path)
    node = _find_node(ws, task)

    if node is None:
        # Fallback: delegate to regex implementation (from org_parser logic)
        return _update_task_property_regex(task, prop_name, prop_value)

    ws.set_property(node, prop_name, prop_value)
    ws.save(fp)
    return fp.read_text(encoding='utf-8')


def _update_task_property_regex(task: OrgTask, prop_name: str, prop_value: str) -> str:
    """Fallback regex-based property update for tasks without :ID:."""
    content = task.file_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    heading_line_idx = task.line_number - 1

    properties_start = None
    properties_end = None

    for i in range(heading_line_idx + 1, min(heading_line_idx + 20, len(lines))):
        stripped = lines[i].strip()
        if stripped == ':PROPERTIES:':
            properties_start = i
        elif stripped == ':END:' and properties_start is not None:
            properties_end = i
            break
        elif re.match(r'^\*+\s', lines[i]):
            break

    if '\n' in prop_value:
        formatted_lines = [f':{prop_name}: |']
        for l in prop_value.split('\n'):
            formatted_lines.append(f'  {l}')
    else:
        formatted_lines = [f':{prop_name}: {prop_value}']

    if properties_start is not None and properties_end is not None:
        prop_line_idx = None
        prop_end_idx = None
        for i in range(properties_start + 1, properties_end):
            if lines[i].strip().startswith(f':{prop_name}:'):
                prop_line_idx = i
                val_match = re.match(r'^:(\w+):\s*(.*)$', lines[i].strip())
                if val_match and val_match.group(2).strip() == '|':
                    prop_end_idx = i + 1
                    while prop_end_idx < properties_end:
                        ns = lines[prop_end_idx].strip()
                        if re.match(r'^:(\w+):\s*(.*)$', ns) or ns == ':END:':
                            break
                        prop_end_idx += 1
                else:
                    prop_end_idx = i + 1
                break

        if prop_line_idx is not None:
            lines[prop_line_idx:prop_end_idx] = formatted_lines
        else:
            for j, new_line in enumerate(formatted_lines):
                lines.insert(properties_end + j, new_line)
    else:
        new_lines = [':PROPERTIES:'] + formatted_lines + [':END:']
        insert_idx = heading_line_idx + 1
        for j, new_line in enumerate(new_lines):
            lines.insert(insert_idx + j, new_line)

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# write_org_file — simple file write (kept for caller compatibility)
# ---------------------------------------------------------------------------

def write_org_file(file_path: Path, content: str) -> None:
    """Write content to an org file."""
    file_path.write_text(content, encoding='utf-8')


# ---------------------------------------------------------------------------
# Workspace accessor for callers that want direct ws operations
# ---------------------------------------------------------------------------

def load_workspace(file_path: Path) -> tuple:
    """Load org-workspace for direct use. Returns (ws, resolved_path)."""
    return _load_ws(file_path)
