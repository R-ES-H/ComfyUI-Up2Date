import re
import json
import os
import sys
import logging
import datetime
import subprocess
import pkg_resources
from rich.console import Console
from rich.theme import Theme
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from rich.theme import Theme

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(THIS_DIR, 'config.json')


def initialize(config_path):
    # Load configuration from the provided path
    if not os.path.exists(config_path):
        sys.stderr.write(f"ERROR: Configuration file not found at {config_path}\n")
        sys.exit(1)
    with open(config_path, 'r', encoding='utf-8') as file:
        config = json.load(file)
    if 'theme' not in config:
        sys.stderr.write("ERROR: 'theme' section not found in config.json. Please check your configuration file.\n")
        sys.exit(1)

    theme_dict = config['theme']
    # Create a custom theme from the theme section in config
    custom_theme = Theme(theme_dict)
    # Initialize logging level from configuration
    log_level = config.get('log_level', 'WARNING').upper()
    numeric_level = getattr(logging, log_level, logging.WARNING)
    
    if not isinstance(numeric_level, int):
        # Default to WARNING if invalid log level is provided
        sys.stderr.write(f"Invalid log level: {log_level}, defaulting to WARNING\n")
        numeric_level = logging.WARNING
    # Initialize Rich console with custom theme
    console = Console(theme=custom_theme, highlight=False, log_time=False)
    # Set up file logger
    logger = logging.getLogger('fileLogger')
    logger.setLevel(numeric_level)

    log_filename = f"log-{datetime.datetime.now().strftime('%Y-%m-%d_%Hh%Mm%Ss')}.log"
    log_path = os.path.join(THIS_DIR, log_filename)
    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setLevel(numeric_level)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.handlers.clear()  # Clear existing handlers to avoid duplicates
    logger.addHandler(handler)
    logger.propagate = False  # Prevent log messages from being propagated to the root logger
    
    # Clean up old log files, keeping only the 3 most recent
    log_files = sorted(
        [f for f in os.listdir(THIS_DIR) if f.startswith('log-')],
        key=lambda x: os.path.getmtime(os.path.join(THIS_DIR, x)),
        reverse=True
    )
    for old_file in log_files[3:]: # Keep only the 3 most recent logs
        try:
            os.remove(os.path.join(THIS_DIR, old_file))
        except OSError as e:
            log_('e', f"error when deleting {old_file}: {e}")

    # Function to log messages both to the file and console

    def log_(level, msg):
        log_levels = {
            'n': 'NOTSET',
            'i': 'INFO',
            'd': 'DEBUG',
            'w': 'WARNING',
            'e': 'ERROR',
            'c': 'CRITICAL'
        }
        
        level = log_levels.get(level.lower(), 'WARNING') # Default to WARNING if invalid level is provided
        numeric_level = getattr(logging, level, logging.WARNING)
        if not isinstance(numeric_level, int):
            numeric_level = logging.WARNING

        logger.log(numeric_level, msg)
        if logger.isEnabledFor(numeric_level):
            # Log to console using Rich with appropriate style
            console.log(f"[{level.lower()}]{msg}[/]", style=level.lower())
    return config, custom_theme, console, log_

config, theme, console, log_ = initialize(CONFIG_PATH)



def requirements_installer(requirements_path):
    # Check if the requirements file exists
    if not os.path.exists(requirements_path):
        log_('w', f"Requirements file not found at {requirements_path}")
        return
    # Read requirements from the file
    with open(requirements_path, 'r') as file:
        requirements = file.read().splitlines()
    for package in requirements:
        if not package:
            continue  # Skip empty lines

        # Check if the package is already installed
        if package in pkg_resources.working_set.by_key:
            log_('i', f"{package} is already installed")
        else:
            log_('d', f"{package} is not installed. Installing...")
            try:
                # Attempt to install the package using pip
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                log_('i', f"{package} has been installed")
            except subprocess.CalledProcessError as e:
                log_('e', f"Failed to install {package}: {e}")


async def menu(menu_items, config):
    primary_color = config['theme'].get('primary', 'white')  # Default to the 'default' color if not specified
    style = Style.from_dict({
        'selected_item': f'reverse bold {primary_color}',  # Style for selected menu item
        'unselected_item': primary_color,  # Style for unselected menu items
    })
    bindings = KeyBindings()  # Create key bindings instance
    current_index = 0  # Initialize the current index

    def get_prompt_text():
        # Create the menu prompt with styles based on whether the item is selected or not
        return [
            (f'class:{"selected_item" if i == current_index else "unselected_item"}', f' {item}  ')
            for i, item in enumerate(menu_items)
        ]
    app = Application(
        key_bindings=bindings,  # Assign key bindings to the application
        layout=Layout(
            HSplit([Window(height=1), Window(FormattedTextControl(get_prompt_text))]) # Create the layout with a title and the menu items
        ),
        full_screen=False,
        style=style  # Apply the defined style to the application
    )
    
    @bindings.add(Keys.Right)
    def move_right(event):
        nonlocal current_index
        current_index = (current_index + 1) % len(menu_items)
        app.invalidate()
    @bindings.add(Keys.Left)
    def move_left(event):
        nonlocal current_index
        current_index = (current_index - 1) % len(menu_items)
        app.invalidate()
    @bindings.add('enter')
    def select(event):
        app.result = current_index
        event.app.exit()
    @bindings.add('escape', eager=True)
    def cancel(event):
        app.result = None
        event.app.exit()

    await app.run_async()
    return app.result


def name_prettifier(directory):
    # Format directory names
    title = re.sub(r'(?i)^comfy(?:ui[_\- ]?|[_\- ])', '', directory)
    # Handle snake_case and kebab-case to spaces
    title = title.replace('-', ' ').replace('_', ' ')
    # Split and rejoin considering uppercase acronyms and capitalized words
    words = []
    for word in title.split():
        # Capitalize the first letter of each word and keep the rest intact
        formatted_word = word[0].upper() + word[1:]
        words.append(formatted_word)
    formatted_title = ' '.join(words)
    return formatted_title


def markdown_fixer(description):
    # Deal with "Text start [w/ warning start [link1](www.link1.com) warning mid [link2](www.link2.com) warning end] text end.""
    segments = []
    pos = 0
    warning_open = False  
    while pos < len(description):
        if description[pos:pos+3] == '[w/' and not warning_open:
            warning_open = True  # Enter warning segment
            segments.append('\n[w/')
            pos += 3
        elif description[pos:pos+3] == '[a/' and warning_open:
            segments.append('][a/')
            pos += 3
        elif description[pos:pos+1] == ')' and warning_open:
            segments.append(')[w/')
            pos += 1
        else:
            segments.append(description[pos])
            pos += 1        
    return ''.join(segments)


def parse_markdown(description):
    segments = []
    # Add a check for warnings and links
    parts = re.split(r'(\[w/.*?\]|\[a/.*?\]\(.*?\)|\[/.*?\])', description)
    for part in parts:
        # Check for warning messages
        if part.startswith('[w/') and part.endswith(']'):
            label = part[3:-1]
            segments.append((label, "warning"))
        # Check for links
        elif part.startswith('[a/') and '(' in part and ')' in part:
            match = re.match(r'\[a/(.*?)\]\((.*?)\)', part)
            if match:
                label, url = match.groups()
                segments.append((label, f"link {url}"))
        else:
            # For ordinary text segments
            segments.append((part, None))
    return segments