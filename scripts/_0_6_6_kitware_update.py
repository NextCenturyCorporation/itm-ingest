from scripts._0_6_5_setup_p2e1 import main as setup_kitware

def main(mongoDB):
    '''Reruns script 065 to avoid messy prod db update'''
    setup_kitware(mongoDB)
        