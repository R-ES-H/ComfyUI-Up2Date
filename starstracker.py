import json
import math
import os
import subprocess
from datetime import datetime, timedelta
from rich.text import Text

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
COMFYUI = os.path.join(THIS_DIR, '../..')
CUSTOM_NODES_DIR = os.path.join(COMFYUI, 'custom_nodes')
MANAGER_DIR = os.path.join(CUSTOM_NODES_DIR, 'ComfyUI-Manager')

CONFIG_PATH = os.path.join(THIS_DIR, 'config.json')
STARSTRACKER = os.path.join(THIS_DIR, 'Starstracker.json')
GITHUB_STATS_PATH = os.path.join(MANAGER_DIR, 'github-stats.json')
CUSTOM_NODE_LIST_PATH = os.path.join(MANAGER_DIR, 'custom-node-list.json')

from utils import markdown_fixer, name_prettifier, parse_markdown, initialize
nodes = []
config, theme, console, log_ = initialize(CONFIG_PATH)


async def starstracker():
    global starstracker_called
    starstracker_called = True

    # Load custom node list
    try:
        with open(CUSTOM_NODE_LIST_PATH, 'r', encoding='utf-8') as alter_file:
            custom_node_list = {
                node['reference']: {
                    'title': node['title'],
                    'description': node['description']
                } for node in json.load(alter_file).get('custom_nodes', [])
            }
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log_('e', f"Error loading custom node list: {e}")
        return
    
    installed_nodes = {node for node in os.listdir(CUSTOM_NODES_DIR) if os.path.isdir(os.path.join(CUSTOM_NODES_DIR, node))}

    # Load current GitHub stats
    try:
        with open(GITHUB_STATS_PATH, 'r', encoding='utf-8') as file:
            current_data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log_('e', f"Error loading GitHub stats: {e}")
        return

    target_date = (datetime.now() - timedelta(config['days_ago'])).replace(tzinfo=None)
    os.chdir(MANAGER_DIR)

    # Retrieve previous GitHub stats data from the relevant commit
    try:
        result = subprocess.run(['git', 'log', '--pretty=format:%H %cI'], capture_output=True, text=True, check=True)
        commits = result.stdout.splitlines()
        previous_commit_hash = next(
            (hash for hash, date_str in (commit.split() for commit in commits)
             if datetime.fromisoformat(date_str.rstrip('Z')).replace(tzinfo=None) <= target_date), commits[-1].split()[0]
        )

        result = subprocess.run(['git', 'show', f'{previous_commit_hash}:{os.path.basename(GITHUB_STATS_PATH)}'], capture_output=True, text=True, check=True)
        previous_data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        log_('e', f"Error retrieving data from commit: {e}")
        return

    starstracker_data = []

    # Process each node for star statistics
    for url, details in current_data.items():
        total_stars = details.get("stars", 0)
        new_stars = total_stars - previous_data.get(url, {}).get("stars", 0)
        last_update_str = details.get("last_update", "1970-01-01 00:00:00")
        try:
            last_update = datetime.strptime(last_update_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            last_update = datetime(1970, 1, 1)  # Fallback date in case of parsing issues
        days_since_update = (datetime.now() - last_update).days

        if url in previous_data and url.split('/')[-1] not in installed_nodes and url not in config['excluded_repos'] and new_stars >= config['minimum_new_stars']:
            
            trend_score = config['trend_factor'] * math.pow(new_stars * 10, 2) / total_stars / 100
            popularity_score = total_stars * config['popularity_factor'] / 100
            update_score = math.exp(-0.05 * (days_since_update + 1) * config['update_factor'] / 100)
            global_score = (trend_score + popularity_score) * update_score
            
            raw_description = custom_node_list.get(url, {}).get('description', "No description available.")
            corrected_description = markdown_fixer(raw_description)
            starstracker_data.append({
                "url": url,
                "title": name_prettifier(url.split('/')[-1]),
                "description": corrected_description,
                "new stars": new_stars,
                "trend score": trend_score,
                "total stars": total_stars,
                "popularity score": popularity_score,
                "updated": days_since_update,
                "update score": update_score,
                "global score": global_score
            })

    # Save starstracker data
    try:
        with open(STARSTRACKER, 'w', encoding='utf-8') as file:
            json.dump(starstracker_data[:config['top_size']], file, ensure_ascii=False, indent=4)
    except IOError as e:
        log_('e', f"Error saving Starstracker data: {e}")
    # Ensure all items have 'global_score'
    for item in starstracker_data:
        if 'global score' not in item:
            item['global score'] = 0  # Assign a default value if missing

    starstracker_data.sort(key=lambda x: x['global score'], reverse=True)

    try:
        with open(STARSTRACKER, 'w', encoding='utf-8') as file:
            json.dump(starstracker_data[:config['top_size']], file, ensure_ascii=False, indent=4)
    except IOError as e:
        log_('e', f"Error loading Starstracker data: {e}")

async def display_starstracker(node_index, config):

    try:
        with open(STARSTRACKER, 'r', encoding='utf-8') as file:
            nodes = json.load(file)
            node = nodes[node_index]
    except (FileNotFoundError, json.JSONDecodeError, IndexError) as e:
        log_('e', f"Error loading Starstracker data: {e}")
        return

    title = node.get('title', 'Unknown')
    url = node.get('url', 'Unknown')
    description = node.get('description', 'No description available.')
    total_stars = node.get('total stars', 'N/A')
    new_stars = node.get('new stars', 'N/A')
    global_score = node.get('global score', 'N/A')
    days_since_update = node.get('updated', 'N/A')
    trend_score = node.get('trend score', 'N/A')
    popularity_score = node.get('popularity score', 'N/A')
    update_score = node.get('update score', 'N/A')

    score_config = {
        'display_score': 'Score: {:.0f}'.format(global_score),
        'display_new_stars': '{} new stars gained last {} days'.format(new_stars, config['days_ago']),
        'display_trend_score': 'Trend score: {:.0f}'.format(trend_score),
        'display_total_stars': '{} github stars'.format(total_stars),
        'display_popularity_score': 'Popularity score: {:.0f}'.format(popularity_score),
        'display_last_update': 'Updated {} days ago'.format(days_since_update),
        'display_update_score': 'Update score factor: {:.2f}'.format(update_score)
    }

    scores = [v for k, v in score_config.items() if config.get(k, False)]
    scores_text = " | ".join(scores)

    repo_color = config['theme']['repo']
    repo_link = Text(title, style=f"link {url} {repo_color}")

    description_text = Text.assemble(*[(segment, style) for segment, style in parse_markdown(description)])

    console.print(repo_link)
    console.print(scores_text)
    console.print(description_text)
    return
    
async def clone_repo(url, destination):
    repo_name = url.split('/')[-1]
    repo_path = os.path.join(destination, repo_name)
    if os.path.exists(repo_path) and os.listdir(repo_path):
        log_('e', f"Repository at {repo_path} already exists and is not empty")
        return
    try:
        subprocess.run(['git', 'clone', url, repo_path], check=True)
        console.print(f"Successfully cloned {url}", style="up_to_date")
    except subprocess.CalledProcessError as e:
        log_('e', f"Error cloning repository {url}: {e}")
