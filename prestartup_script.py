import os
import sys
import json
import asyncio
import time

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
COMFYUI = os.path.join(THIS_DIR, '../..')
CUSTOM_NODES_DIR = os.path.join(COMFYUI, 'custom_nodes')
sys.path.append(THIS_DIR)
STARSTRACKER = os.path.join(THIS_DIR, 'Starstracker.json')
CONFIG_PATH = os.path.join(THIS_DIR, 'config.json')
REQUIREMENTS_PATH = os.path.join(THIS_DIR, 'requirements.txt')

from starstracker import starstracker, display_starstracker, clone_repo
from utils import menu, initialize, requirements_installer, log_

config, theme, console, log_ = initialize(CONFIG_PATH)
requirements_installer(REQUIREMENTS_PATH)


def display_header():
    if config['display_header']:
        for line in config['header']:
            console.print(line, style='header')
    else:
        log_('i', "Header display is disabled in config")

display_header()

async def display_timer(timeout_duration, config):
    start_time = time.time()
    print() 
    while True:
        remaining_time = int(timeout_duration - (time.time() - start_time))
        print(f"\033[s{config['default_choice']} in {remaining_time} seconds", end='\033[u', flush=True)
        if remaining_time <= 0:
            log_('d', f"\r\033[2K Time's up! Choosing default: {config['default_choice']}")
            return
        await asyncio.sleep(1)


async def main():
    # Initialize main menu index
    node_index = 0
    menu_items = ['Trending Nodes', 'Update All', 'Run ComfyUI']
    menu_items_st = ['Next', 'Install', 'Back']
    choice_index = 0
    menu_loop = True
    timer = True

    # Main menu loop
    while menu_loop:
        try:
            if timer:
                # Start display timer asynchronously
                timer_task = asyncio.create_task(display_timer(config.get('timeout', 10), config))
                # Wait for menu choice with a timeout
                choice_index = await asyncio.wait_for(menu(menu_items, config), config.get('timeout', 10))
                # Cancel the timer if user makes a choice
                timer_task.cancel()
            if not timer:
                # Wait for menu choice without a timeout
                choice_index = await asyncio.wait_for(menu(menu_items, config), None)
            choice = menu_items[choice_index].lower()
        except asyncio.TimeoutError:
            # Handle timeout by choosing default option
            choice = config['default_choice'].lower()
        
        # Handle the different choices in the main menu
        if choice == 'update all':
            log_('d',"Executing update choice")
            from updater import update
            await update()
        elif choice == 'run':
            log_('d', "Executing run choice")
            console.print('\nConfig :\n', CONFIG_PATH, style='info')
            # Exit script after displaying config
            sys.exit()
        elif choice == 'trending nodes':
            timer = False
            log_('d', "Executing install choice")
            await starstracker()
            try:
                # Load and display nodes from Starstracker.json
                with open(STARSTRACKER, 'r', encoding='utf-8') as file:
                    nodes = json.load(file)
                    node_index = 0 
                    # Loop through the nodes for installation
                    while node_index < len(nodes):
                        await display_starstracker(node_index, config)
                        choice_index_st = await menu(menu_items_st, config)
                        choice_st = menu_items_st[choice_index_st].lower()
                        if choice_st == 'next':
                            node_index += 1
                        elif choice_st == 'install':
                            # Install selected node
                            url = nodes[node_index].get('url', 'Unknown')
                            await clone_repo(url, CUSTOM_NODES_DIR)
                        elif choice_st == 'back':
                            timer = False
                            break
            except (FileNotFoundError, json.JSONDecodeError) as e:
                log_('e', f"Error loading Starstracker.json: {e}")
            continue
        break
        
log_('d', "Starting script execution")
asyncio.run(main())
log_('d', "Main function execution completed")


