from lambda_handler import lambda_handler
import shutil, os

base_dir = os.path.dirname(__file__)
tccc_folder = os.path.join(base_dir, '..', 'TCCC-Trainer', '00a2ceb8-83cc-4009-a3a7-8cfbc3671c43_202602188')
csv_path = os.path.join(tccc_folder, '00a2ceb8-83cc-4009-a3a7-8cfbc3671c43_202602188.csv')
json_path = os.path.join(tccc_folder, '00a2ceb8-83cc-4009-a3a7-8cfbc3671c43_202602188.json')

shutil.copy(csv_path, 'C:/tmp/')
shutil.copy(json_path, 'C:/tmp/')

fake = {'Records': [
    {
        's3': {
            'bucket':  {
                'name': 'random'
            },
            'object': {
                'key': '00a2ceb8-83cc-4009-a3a7-8cfbc3671c43_202602188.csv'
            }
        }
    }
]}

lambda_handler(fake, None)