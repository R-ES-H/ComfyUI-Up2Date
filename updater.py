import os
import re
from rich.console import Console
from rich.text import Text
from rich.progress import (
    Progress, 
    BarColumn, 
    TextColumn, 
    SpinnerColumn, 
    MofNCompleteColumn,
    TimeRemainingColumn, 
    TimeElapsedColumn,
    ProgressColumn,
    Task
)
from git import Repo, GitCommandError
from git.exc import NoSuchPathError, InvalidGitRepositoryError

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
COMFYUI = os.path.join(THIS_DIR, '../..')
CUSTOM_NODES_DIR = os.path.join(COMFYUI, 'custom_nodes')
MANAGER_DIR = os.path.join(CUSTOM_NODES_DIR, 'ComfyUI-Manager')

CONFIG_PATH = os.path.join(THIS_DIR, 'config.json')


from utils import name_prettifier, initialize, log_

config, theme, console, log_ = initialize(CONFIG_PATH)

secondary = "secondary"

class StyledProgressColumn(ProgressColumn):
    # Initialize column with the given type and additional arguments
    def __init__(self, column_type, *args, **kwargs):
        self.column_instance = column_type(*args, **kwargs)
    
    # Render method to apply custom style for progress columns
    def render(self, task: Task) -> Text:
        text = self.column_instance.render(task)
        text.style = secondary
        return text

    # Fallback for other attributes
    def __getattr__(self, name):
        return getattr(self.column_instance, name)


def git(dir_path):
    try:
        repo = Repo(dir_path) # Initialize the repository from local directory
        origin = repo.remotes.origin # Get the origin remote
        repo_url = repo.remotes.origin.url # Get the repository URL
        log_('d', f"\nProcessing {dir_path}")
        # Find the default branch
        try:
            default_branch = repo.git.symbolic_ref('refs/remotes/origin/HEAD').split('/')[-1]
        except (GitCommandError, ValueError) as e:
            error_message = f"error during default branch detection: {e}"
            return "error", error_message, dir_path

        if not default_branch:
            error_message = "Impossible to determine the default branch."
            return "error", error_message, dir_path

        # Capture the SHA of the commit before pulling
        before_pull_sha = repo.head.commit.hexsha
        # Reset to a clean state
        repo.git.reset('--mixed')
        # Stash local modifications if necessary
        stash_result = repo.git.stash('push', '-m', 'auto-stash-before-pull')
        # Perform the pull
        fetch_result = origin.pull(allow_unrelated_histories=True)
        # Pop stashed changes if necessary
        if stash_result != 'No local changes to save':
            repo.git.stash('pop')
        # Capture the SHA of the commit after the pull
        after_pull_sha = repo.head.commit.hexsha
        infos = ""
        new_commits = []
        # Get the logs of commits between the two SHAs
        if before_pull_sha != after_pull_sha:
            # Extract new commits introduced by the pull
            new_commits = list(repo.iter_commits(f'{before_pull_sha}..{after_pull_sha}'))

        if config.get('display_fetch'):
            fetches = [f"{fetch.ref.name} {fetch.note}" for fetch in fetch_result]
            infos += "\n".join(fetches)
        # If the display_logs config is enabled, add commit logs to infos
        if config.get('display_logs'):
            infos += get_commit_logs(new_commits)
        # Check if there is a README.md file and add its diff to infos if it was modified
        if config.get('display_readme'):
            readme_path = os.path.join(dir_path, 'README.md') # Path to the README.md file
            if os.path.exists(readme_path):
                diff = repo.git.diff(f'{before_pull_sha}..{after_pull_sha}', '-p', readme_path) #
                log_('d', f"Diff for README.md: {diff}")
                if diff:
                    infos += f"\n\nReadme.md update :\n{get_readme_modifs(diff)}"
                    log_('d', "readme.md update added to infos")

        return ("outdated", infos, repo_url) if before_pull_sha != after_pull_sha else ("UTD", "", repo_url)
    
    except (NoSuchPathError, InvalidGitRepositoryError, GitCommandError, ValueError, PermissionError, OSError, Exception) as e:
        error_type = e.__class__.__name__
        error_message = f"{error_type}: {e}"
        return "error", error_message, repo_url


def get_commit_logs(commits):
    logs = []
    for commit in commits:
            log_entry = []
            display_config = config.get
            if display_config('display_commit'):
                    log_entry.append(f"{commit.hexsha[:7]}:")
            if display_config('display_date'):
                    log_entry.append(f"{commit.authored_datetime}:")
            if display_config('display_author'):
                    log_entry.append(f"{commit.author.name}")
            if display_config('display_email'):
                    log_entry.append(f"<{commit.author.email}>")
            clean_message = " ".join(line.strip() for line in commit.message.splitlines() if line.strip())
            log_entry.append(clean_message)
            logs.append("\n  ".join(log_entry).strip())
            logs.append("")
    return "\n".join(logs)


def get_readme_modifs(diff):
    # Use a regular expression to extract the modified lines
    modified_lines = re.findall(r'^\+(.*)$', diff, re.MULTILINE)
    
    # Group the lines into paragraphs and retrieve the section titles
    paragraphs, current_paragraph = [], []
    current_title = None
    
    # Iterate through each modified line
    for line in modified_lines:
        line = line.strip()
        if re.match(r'^#+ ', line):
            # If there's a current paragraph, append it as a tuple (title, paragraph)
            if current_paragraph:
                paragraphs.append((current_title, '\n'.join(current_paragraph)))
                log_('d', "paragraph is added")
                current_paragraph = []
            current_title = line
        elif line:
            current_paragraph.append(line)
            log_('d', "line is added to current_paragraph")
        else:
            if current_paragraph:
                paragraphs.append((current_title, '\n'.join(current_paragraph)))
                current_paragraph, current_title = [], None
                log_('d', "paragraph is reset and added to paragraphs")
    # After loop, if any paragraph remains, append it to paragraphs
    if current_paragraph:
        paragraphs.append((current_title, '\n'.join(current_paragraph)))
        log_('d', "last paragraph is added to paragraphs")
    
    # Format the output to include the section titles
    readme_modifs = [f"{title}\n{paragraph}" if title else paragraph for title, paragraph in paragraphs]
    log_('d', 'readme_modifs is created')

    return '\n\n'.join(readme_modifs)


async def update():
    log_('i', 'Updating ComfyUI repository')
    fetch_flag, infos, url = git(COMFYUI)
    display(fetch_flag, 'ComfyUI', infos, url)

    log_('i', 'Updating custom_nodes repositories')
    dirs = [dir for dir in os.scandir(CUSTOM_NODES_DIR) if dir.is_dir() and dir.name != "__pycache__"]

    def update_repo(task, dir):
            # Get the local path of the repository
            dir_path = dir.path
            # Prettify the repository name for display purposes
            repo_pretty = name_prettifier(dir.name)
            # Retrieve state, informations, and URLof installed custom nodes
            fetch_flag, infos, url = git(dir_path)

            progress.update(task)
            display(fetch_flag, repo_pretty, infos, url)
            progress.update(task, advance=1)

    with Progress(
        StyledProgressColumn(TextColumn, text_format="{task.description}"),
        StyledProgressColumn(TextColumn, text_format="{task.percentage:>3.0f}%"),
        StyledProgressColumn(BarColumn, bar_width=30, style='primary', complete_style='primary'),
        SpinnerColumn(style='primary'),  
        StyledProgressColumn(MofNCompleteColumn),
        TextColumn("-", style='primary'), 
        StyledProgressColumn(TimeRemainingColumn),
        TextColumn("-", style='primary'), 
        StyledProgressColumn(TimeElapsedColumn),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Updating repositories...", total=len(dirs))
        for dir in dirs:
            update_repo(task, dir)


def display(fetch_flag, repo_name, infos, url):
    # Nodes names with rich custom style and hyperlinks to their repositories
    repo_link = Text(repo_name, style=f"link {url} {config['theme']['repo']}")
    
    # Clear the previous line for each loop iteration if 'compact' in config is true. Overwrite up-to-date nodes.
    if config.get('compact'):
        console.print('\033[F\033[K', end='')
        
    if fetch_flag == "UTD":
        console.print('🗸', repo_link, style="up_to_date")
        log_('i', f"{repo_name} is up to date")
    elif fetch_flag == "outdated":
        log_('w', f"🡅 {repo_link} \n {infos} \n")
    elif fetch_flag == "error":
        log_('e', f"🞫 {repo_link} \n {infos} \n")
    else:
        log_('e', f"?! {repo_link} \n {infos} \n")


