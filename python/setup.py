from rdt_utils import *

def interactive_create_config() -> dict[str, str]:
    global remote_host, user_home_remote, clangd_path
    if not remote_host:
        remote_host = input('Please enter remote host: ').strip()
    if not user_home_remote:
        user_home_remote = input('Please enter user_home_remote: ')
    clangd_path = find_clangd_exe(error_on_failure=False)
    if not clangd_path:
        clangd_path = input('Please enter path to clangd executable: ')
    return {'remote_host': remote_host, 'user_home_remote': user_home_remote, 'clangd_path': clangd_path}

    


if __name__ == '__main__':
    ########## Ensure basic directory structure of ~/.remote-development-tools ############
    if not os.path.exists(rdt_root_path):
        os.makedirs(rdt_root_path)

    project_templates_path = os.path.join(rdt_root_path, 'project-templates')
    remote_headers_path = os.path.join(rdt_root_path, 'remote-header-files')

    if not os.path.exists(project_templates_path):
        os.makedirs(project_templates_path)


    if not os.path.exists(remote_headers_path):
        os.makedirs(remote_headers_path)
    #######################################################################################



    ########## Ensure basic files in ~/.remote-development-tools ############

    # Ensure RemoteDevelopmentTools config json file
    if not os.path.exists(rdt_config_path):
        dct = interactive_create_config()
        with open(rdt_config_path, 'w') as f:
            json.dump(dct, f)

    tracked_projects_path = os.path.join(rdt_root_path, 'tracked-projects.json')
    if not os.path.exists(tracked_projects_path):
        with open(tracked_projects_path, 'w') as f:
            json.dump({}, f)

    if not os.path.exists(rdt_state_path):
        with open(rdt_state_path, 'w') as f:
            json.dump({'active_projects': []}, f)

    if not os.path.exists(definition_mappings_path):
        with open(definition_mappings_path, 'w') as f:
            json.dump({}, f)

    # definition_mappings_path = os.path.join(rdt_root_path, 
    #######################################################################################










