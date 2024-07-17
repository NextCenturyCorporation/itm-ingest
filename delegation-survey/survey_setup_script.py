import subprocess

subprocess.run(['python', 'convert_adms_for_delegation.py'])

inputs = b'\n2\ny\ny\ny\n'

process = subprocess.Popen(['python', 'update_survey_config.py'], stdin=subprocess.PIPE)
process.communicate(input=inputs)
