from ntpath import isdir
import subprocess
from parseargs import parse_args
from rdt_utils import *
from uuid import uuid4
from itertools import cycle
from sync_project import sync_project, PUSH, PULL
from shutil import copy2
from typing import Any, Iterable
import datetime as dt



user_home_path = normalize_path(os.path.expanduser('~'), '\\')
rdt_home_path = os.path.join(user_home_path, '.remote-development-tools')
tracked_projects_path = os.path.join(rdt_home_path, 'tracked-projects.json')


ProjectEntry: TypeAlias = dict[str, str|int]
ProjectsDict: TypeAlias = dict[str, ProjectEntry]

def load_tracked_projects_dict() -> ProjectsDict:
    with open(tracked_projects_path, 'r') as f:
        dct: ProjectsDict = json.load(f)
    return dct

if not os.path.exists(tracked_projects_path):
    with open(tracked_projects_path, 'w') as f:
        json.dump({}, f)

tracked_projects_dict = load_tracked_projects_dict()

def logtmp(msg: str):
    with open('C:/Users/sjber/Coding/RemoteDevelopmentTools/tmp.txt', 'a') as f:
        f.write(f'\n{msg}\n')


# Sync Modes
NO_SYNC     = 0 #Do not sync with remote at all
ON_WRITE    = 1 #Sync every time any buffer (file) in the project is written
ON_N_WRITES = 2 #Same as ON_WRITE, except it syncs every Nth time a project file buffer is written instead of every time


@dataclass(frozen=True)
class ProjectType:
    language_id: str
    build_type: str
    subtype: str

    @classmethod
    def parse(cls, s: str) ->   "ProjectType":
        if not s:
            return cls('', '', '')
        lang, rest = s.split(':')
        if rest:
            if '/' in rest:
                bt, st = rest.split('/')
            else:
                bt = rest
                st = ''
        else:
            bt = ''
            st = ''
        return cls(lang, bt, st)


class Project:
    def __init__(self, arg: str|dict[str, str]):
        if isinstance(arg, str):
            if arg in tracked_projects_dict:
                self.dct = tracked_projects_dict[arg]
            else:
                self.dct = {}
                for id, proj in tracked_projects_dict.items():
                    if (proj['name'] == arg) or (proj['root_path'] == arg):
                        self.dct = proj
                        break
                if not self.dct:
                    raise RuntimeError('Error: Failed to find project in tracked_projects')

        elif isinstance(arg, dict):
            self.dct: dict = arg
        else:
            raise TypeError('Error, arg must be str (project_name)')
        # Exisistence of self.dct is now assured from this point on

        if 'id' not in self.dct:
            self.dct['id'] = str(uuid4())
        if 'root_path' not in self.dct:
            self.dct['root_path'] = os.getcwd()
            # raise ValueError('Error, missing root_path from Project dct')
        self.dct['root_path'] = normalize_path(self.dct['root_path'])
        if 'name' not in self.dct:
            self.dct['name'] = self.dct['root_path'].split('/')[-1]
        if 'creation_timestamp' not in self.dct:
            self.dct['creation_timestamp'] = dt.datetime.now().isoformat()
        if 'last_sync_timestamp' not in self.dct:
            self.dct['last_sync_timestamp'] = self.dct['creation_timestamp']


        self.id = self.dct['id']
        self.name = self.dct['name']
        self.root_path: str = self.dct['root_path']
        self.sync_mode = self.dct.get('sync_mode', ON_WRITE)
        self.creation_timestamp = self.dct['creation_timestamp']
        self.last_sync_timestamp = self.dct['last_sync_timestamp']
        self.writes_per_sync = 1 if self.sync_mode != ON_N_WRITES else self.dct.get('writes_per_sync', 5)
        self.write_count = self.dct.get('write_count', 0)
        self.project_type = ProjectType.parse(self.dct.get('project_type', ''))
        if self.project_type.build_type == 'cmake':
            pass
        self.build_command_prefix = ''
        build_type = self.project_type.build_type
        match build_type:
            case 'xcode':
                self.build_command_prefix = 'xcodebuild'
                build_loc_name = f'{self.name}.xcodeproj'
                self.build_location = normalize_path(os.path.join(self.root_path, build_loc_name))
            case 'cmake':
                self.build_command_prefix = 'cmake --build'
                self.build_location = normalize_path(os.path.join(self.root_path, 'build'))
            case 'g++':
                self.build_command_prefix = 'g++'


    def build(self, remote=False):
        print('Running build command')
        build_type = self.project_type.build_type
        subtype = self.project_type.subtype
        root_path = self.root_path if not remote else clangd_path_mapping_path(self.root_path, LOCAL_TO_REMOTE)
        match build_type:
            case 'xcode':
                build_loc = f'{self.name}.xcodeproj'
                if subtype:
                    subtype = subtype[:-2] + subtype[-2:].upper()
                else:
                    subtype = 'iOS'
                cmd = f"xcodebuild -project {build_loc} -scheme {self.name} -allowProvisioningUpdates DEVELOPMENT_TEAM={development_team} CODE_SIGN_STYLE=Automatic"
                full_cmd = f'cd {root_path} && {cmd}'
                if remote:
                    res = remote_execute(full_cmd)
                    print(res)
                else:
                    subprocess.run(shlex.split(cmd))
        pass

#     build_project_command = ['cd', remote_path, '&&', 'xcodebuild', '-scheme', project_name, '-project', f'{project_name}.xcodeproj',
#                              '-allowProvisioningUpdates', f'DEVELOPMENT_TEAM="{development_team}"', 'CODE_SIGN_STYLE=Automatic']


    def as_dict(self):
        return {'id': self.id, 'name': self.name, 'root_path': self.root_path, 'sync_mode': self.sync_mode,
                'creation_timestamp': self.creation_timestamp, 'last_sync_timestamp': self.last_sync_timestamp,
                'writes_per_sync': self.writes_per_sync, 'write_count': self.write_count}


    def save(self):
        global tracked_projects_dict
        tracked_projects_dict = load_tracked_projects_dict()
        tracked_projects_dict[self.id] = self.as_dict()
        with open(tracked_projects_path, 'w') as f:
            json.dump(tracked_projects_dict, f)


    def increment_write_count(self):
        self.write_count = (self.write_count + 1) % self.writes_per_sync

    def set(self, **kwargs):
        save = kwargs.get('save', False)
        for key, val in kwargs.items():
            if key == 'save':
                continue
            match key:
                case 'id':
                    self.id = val
                case 'name':
                    self.name = val
                case 'root_path':
                    self.root_path = val
                case 'sync_mode':
                    self.sync_mode = val
                case 'creation_timestamp':
                    self.creation_timestamp = val
                case 'last_sync_timestamp':
                    self.last_sync_timestamp = val
                case 'project_type':
                    if isinstance(val, ProjectType):
                        self.project_type = val
                    elif isinstance(val, list) or isinstance(val, tuple):
                        self.project_type = ProjectType(*val)
                    elif isinstance(val, str):
                        self.project_type = ProjectType.parse(val)
                    else:
                        raise TypeError(f"Error, invalid type when setting 'project_type': {type(val)}")
                case _:
                    raise KeyError(f'Error, invalid key passed to Project.set: {key}')
        if save:
            self.save()

    def sync(self, sync_direction=PUSH):
        logtmp('SYNC WAS CALLED SYNC WAS CALLED SYNC WAS CALLED\n\n\n')
        sync_project(self.root_path, sync_direction, dry_run=False)
        self.increment_write_count()
        self.write_count = (self.write_count + 1) % self.writes_per_sync
        with open('C:/Users/sjber/Coding/RemoteDevelopmentTools/tmp.txt', 'a') as f:
            f.write(f'syncing with write_count: {self.write_count}')
        self.last_sync_timestamp = dt.datetime.now().isoformat()
        self.save()

    def __str__(self):
        return json.dumps(self.as_dict())

    def __repr__(self):
        return json.dumps(self.as_dict())

    def __eq__(self, other):
        other_dct: dict = other if isinstance(other, dict) else ({} if not isinstance(other, Project) else other.dct)
        if not other_dct:
            return False
        for key, val in self.dct.items():
            if val != other_dct[key]:
                return False
        return True


def load_tracked_projects() -> dict[str, Project]:
    tracked_projects: dict[str, Project] = {}
    with open(tracked_projects_path, 'r') as f:
        dct = json.load(f)

    for id, proj_dct in dct.items():
        tracked_projects[id] = Project(proj_dct)
    return tracked_projects


def track_existing_project(root_path: str, **kwargs) -> Project:
    id = kwargs.get('id', str(uuid4()))
    creation_timestamp = kwargs.get('creation_timestamp', dt.datetime.now().isoformat())
    last_sync_timestamp = kwargs.get('last_sync_timestamp', creation_timestamp)
    root_path = normalize_path(root_path)
    name = kwargs.get('name', root_path.split('/')[-1])
    sync_mode = kwargs.get('sync_mode', ON_N_WRITES)
    writes_per_sync = kwargs.get('writes_per_sync', 5)
    write_count = 0
    dct = {'id': id, 'name': name, 'root_path': root_path, 'sync_mode': sync_mode,
            'creation_timestamp': creation_timestamp, 'last_sync_timestamp': last_sync_timestamp,
            'writes_per_sync': writes_per_sync, 'write_count': write_count}
    project = Project(dct)
    project.save()
    return project


def initialize_git_repo(root_path: str = ''):
    if not root_path:
        root_path = os.getcwd()
    output = run_process('git init .')
    print(output)

def create_new_project(root_path: str = '', primary_language: str = '', *subtypes:str):
    if not root_path:
        root_path = os.getcwd()

    if not os.path.exists(root_path):
        os.makedirs(root_path, exist_ok=True)

    initialize_git_repo(root_path)
    if not primary_language:
        return


    project_templates_root = os.path.join(rdt_root_path, 'project-templates')
    template_sep = '_'
    template_str = f'{primary_language}{template_sep}{template_sep.join(subtypes)}'.lower()

    template_path = project_templates_root
    for part in template_str.split(template_sep):
        template_path = os.path.join(template_path, part)

    if not os.path.exists(template_path):
        raise RuntimeError(f'Error, unable to find project template at location: {template_path}')

    if not os.path.isdir(template_path):
        raise RuntimeError(f'Error, a file (not a directory) was found at template location: {template_path}')

    copy2(template_path, root_path)


def configure_project(project: Project|dict[str,str]|str, **kwargs):
    if isinstance(project, str):
        project = tracked_projects.get(project, '')
        if not project:
            raise RuntimeError(f'Failed to load project from provided argument project: {project}')
        elif not isinstance(project, Project):
            raise RuntimeError(f'Error, failed to load {project} as a Project')
    elif isinstance(project, dict):
        project = Project(project)

    for key, val in kwargs.items():
        if not key in project.dct:
            raise KeyError(f'Error, invalid key provided to configure_project.  key: {key}')
        project.dct[key] = val

    project.save()



def build_project(project: Project|str):
    tracked_projects_dict
    # xcodebuild -project iosapptest2.xcodeproj -scheme iosapptest2 -destination 'generic/platform=iOS Simulator'
    


def get_subcommand(arg_dct: dict):
    subcommands = ['sync', 'autosync', 'configure', 'add', 'track', 'build']
    for arg in arg_dct['args']:
        if arg.lower() in subcommands:
            return arg.lower()




print(tracked_projects_path)

if __name__ == '__main__':



    with open('C:/Users/sjber/Coding/RemoteDevelopmentTools/tmp.txt', 'a') as f:
        f.write(f'THE FILE IS AT LEAST FUCKING RUNNING\ntracked_projects_path: {tracked_projects_path}\n')

    arg_dct = parse_args(sys.argv)
    long_flags = arg_dct['long']
    short_flags = arg_dct['short']
    plain_args = arg_dct['args']

    print(f'long_flags: {long_flags}')
    print(f'short_flags: {short_flags}')
    print(f'plain_args: {plain_args}')


    for k, v in long_flags.items():
        long_flags[k.lower()] = v

    for k, v in short_flags.items():
        short_flags[k.lower()] = v

    cmd = get_subcommand(arg_dct)

    remote_host = ''
    root_path = sys.argv[-1] if len(sys.argv) > 1 else ''
    if not root_path or not os.path.exists(root_path):
        root_path = normalize_path(get_project_root_path(os.getcwd()))

    print(f'root_path: {root_path}')
    print(f'cmd: {cmd}')

    for arg in sys.argv[1:]:
        if arg.startswith('--remote-host='):
            remote_host = arg.split('=')[1]
            break

    if not os.path.exists(tracked_projects_path):
        with open(tracked_projects_path, 'w') as f:
            json.dump({}, f)

    tracked_projects = load_tracked_projects()
    project = None
    for id, proj in tracked_projects.items():
        if proj.root_path == root_path:
            project = proj
            break


    if project is not None:
        for _ in range(10):
            print('PROJECT IS NOT NONE')
        if cmd == 'sync':
            # Immediately sync regardless of project's sync settings.  Does not affect sync settings (including write_count) in any way
            # For use mainly by command line commands which are wrappers around this file's functionality
            # The specific command to use this is: proj sync
            project.sync()
            exit()
        elif cmd == 'autosync':
            # This command is really only for use by the nvim plugin, which calls this file with autosync as an argument
            # to trigger this behavior: syncing or not syncing based on the project's auto sync settings
            if project.sync_mode == ON_WRITE:
                project.sync()
            elif project.sync_mode == ON_N_WRITES:
                if project.write_count == 0:
                    project.sync()
                else:
                    project.increment_write_count()
                    project.save()
        elif cmd == 'configure':
            print('In configure code')
            if 'show' in short_flags or 'show' in long_flags:
                keys = ['name', 'id', 'root_path', 'sync_mode', 'creation_timestamp', 'last_sync_timestamp', 'writes_per_sync', 'write_count']
                for key in keys:
                    val = project.dct[key]
                    print(f'{key}: {val}')
                exit()

            if 'syncmode' in short_flags or 'syncmode' in long_flags:
                for _ in range(10):
                    print('IN SYNCMODE BRANCH')
                sync_mode: str = short_flags.get('syncmode', long_flags.get('syncmode', '')).lower()
                if sync_mode == 'never':
                    project.sync_mode = 0
                elif sync_mode == 'always':
                    project.sync_mode = 1
                    project.write_count = 0
                    project.writes_per_sync = 1
                elif sync_mode == 'interval':
                    project.sync_mode = 2
                elif isinstance(sync_mode, int):
                    if 0 <= sync_mode <= 2:
                        project.sync_mode = sync_mode

            # It's kind of annoying, but I already settled on writes_per_sync as the name in the python code.
            # However it is IMO too long for a command flag, so I settled on 'interval' for the CL flag name
            if 'interval' in short_flags or 'interval' in long_flags:
                interval: int = short_flags.get('interval', long_flags.get('interval', project.writes_per_sync))
                project.writes_per_sync = interval

            project.save()

        elif cmd == 'build':
            print('cmd == \'build\'')
            remote = True if (project.project_type.build_type == 'xcode' and sys.platform == 'win32') else False
            project.build(remote=remote)

    else:
        # project is None, meaning the current project is not already tracked
        if cmd == 'add' or cmd == 'track':
            # If cmd is 'add' or 'track', track the project that cwd is inside of
            proj = track_existing_project(root_path)
            print(f'newly tracked project: {str(proj)}')



        logtmp(f'at end of file, project: {str(project)}')


#comment test





