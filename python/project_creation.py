from rdt_utils import *
from sync_project import sync_project, PUSH, PULL



def create_project_base(root_path: str, project_name: str = ''):
    '''
    Create an essentially empty project at the given `root_path`.
    The only files created are a .gitignore and initializing the git repo.

    If `root_path` is an existing directory and `project_name`
    is '', the project is created exactly at `root_path` and
    `project_name` is set to the directory name of `root_path`

    If `root_path` is an existing directory and `project_name`
    is NOT '', the project is created at {`root_path`}/{`project_name`}

    If `root_path` is NOT an existing directory and `project_name` is NOT
    '', if the final path component of `root_path` is `project_name`,
    then the project is created at exactly `root_path`.  Otherwise (if
    the final component of `root_path` it NOT `project_name`), then the
    project is created at {`root_path`}/{`project_name`}
    '''
    if not os.path.isabs(root_path):
        root_path = os.path.join(os.getcwd(), root_path)
    if not project_name:
        if os.path.exists(root_path):
            project_name = os.path.split(root_path)[-1]
        else:
            root, project_name = os.path.split(root_path)
            if not os.path.exists(root):
                raise RuntimeError(f'Error, root_path must be a path to an already existing directory, or a path directly inside of an already existing directory')




    pass


# def create_ios_project(root_path: str, project_name: str = ''):
#     '''
#     Create an ios project at the given `root_path`
#
#     If `root_path` is an existing directory and `project_name`
#     is '', the project is created exactly at `root_path` and
#     `project_name` is set to the directory name of `root_path`
#
#     If `root_path` is an existing directory and `project_name`
#     is NOT '', the project is created at {`root_path`}/{`project_name`}
#
#     If `root_path` is NOT an existing directory and `project_name` is NOT
#     '', if the final path component of `root_path` is `project_name`,
#     then the project is created at exactly `root_path`.  Otherwise (if
#     the final component of `root_path` it NOT `project_name`), then the
#     project is created at {`root_path`}/{`project_name`}
#     '''
#     # if root_path is not an absolute path, make it an absolute path rooted at the cwd
#     # i.e. treat it as a relative path from the cwd if it is not an absolute path
#     if not os.path.isabs(root_path):
#         root_path = os.path.join(os.getcwd(), root_path)
#     if not project_name:
#         if os.path.exists(root_path):
#             project_name = os.path.split(root_path)[-1]
#         else:
#             root, project_name = os.path.split(root_path)
#             if not os.path.exists(root):
#                 raise RuntimeError(f'Error, root_path must be a path to an already existing directory, or a path directly inside of an already existing directory')
#
#             # raise RuntimeError(f'Error, 
#
#     remote_path = clangd_path_mapping_path(root_path)
#     development_team = '6DDGC468AY'
#
#     # Ensure the existence of a directory at remote_path on the remote_host, 
#     # creating it and any intermediate directories if it does not already exist
#     ensure_remote_directory(remote_path)
#
#     # create and execute the remote command (remote_execute executes the command on remote_host over ssh)
#     remote_cmd = f'cd {remote_path} && swift package init --type executable'
#     remote_execute(remote_cmd)
#
#     build_server_cmd = f'cd {remote_path} && xcode-build-server config -scheme {project_name} -project {project_name}.xcodeproj'
#     remote_execute(build_server_cmd)
#
#
#     # actually literally build the project, this generates buildServer.json which is necessary for the swift language server to work
#     build_project_command = ['cd', remote_path, '&&', 'xcodebuild', '-scheme', project_name, '-project', f'{project_name}.xcodeproj',
#                              '-allowProvisioningUpdates', f'DEVELOPMENT_TEAM="{development_team}"', 'CODE_SIGN_STYLE=Automatic']
#     remote_execute(build_project_command)
#
#
#     # rsync the remotely created directory to this machine
#     sync_project(root_path, sync_direction=PULL, dry_run=False)


def create_ios_project(root_path: str, project_name: str = ''):
    '''
    Create an ios project at the given `root_path`

    If `root_path` is an existing directory and `project_name`
    is '', the project is created exactly at `root_path` and
    `project_name` is set to the directory name of `root_path`

    If `root_path` is an existing directory and `project_name`
    is NOT '', the project is created at {`root_path`}/{`project_name`}

    If `root_path` is NOT an existing directory and `project_name` is NOT
    '', if the final path component of `root_path` is `project_name`,
    then the project is created at exactly `root_path`.  Otherwise (if
    the final component of `root_path` it NOT `project_name`), then the
    project is created at {`root_path`}/{`project_name`}
    '''
    # if root_path is not an absolute path, make it an absolute path rooted at the cwd
    # i.e. treat it as a relative path from the cwd if it is not an absolute path
    if not os.path.isabs(root_path):
        root_path = os.path.join(os.getcwd(), root_path)
    if not project_name:
        if os.path.exists(root_path):
            project_name = os.path.split(root_path)[-1]
        else:
            root, project_name = os.path.split(root_path)
            if not os.path.exists(root):
                raise RuntimeError(f'Error, root_path must be a path to an already existing directory, or a path directly inside of an already existing directory')

            # raise RuntimeError(f'Error, 

    remote_path = clangd_path_mapping_path(root_path)
    development_team = '6DDGC468AY'
    root_dir_name = os.path.split(remote_path)[1]
    source_path = normalize_path(os.path.join(remote_path, root_dir_name))

    # Ensure the existence of a directory at remote_path on the remote_host, 
    # creating it and any intermediate directories if it does not already exist
    # ensure_remote_directory(remote_path)
    # This will automatically create the remote root path if it doesnt already exist
    ensure_remote_directory(source_path)

    # ensure_remote_directory p

    # create and execute the remote command (remote_execute executes the command on remote_host over ssh)
    remote_cmd = f'cd {remote_path} && swift package init --type executable'
    remote_execute(remote_cmd)

    build_server_cmd = f'cd {remote_path} && xcode-build-server config -scheme {project_name} -project {project_name}.xcodeproj'
    remote_execute(build_server_cmd)


    # actually literally build the project, this generates buildServer.json which is necessary for the swift language server to work
    build_project_command = ['cd', remote_path, '&&', 'xcodebuild', '-scheme', project_name, '-project', f'{project_name}.xcodeproj',
                             '-allowProvisioningUpdates', f'DEVELOPMENT_TEAM="{development_team}"', 'CODE_SIGN_STYLE=Automatic']
    remote_execute(build_project_command)


    # rsync the remotely created directory to this machine
    sync_project(root_path, sync_direction=PULL, dry_run=False)









