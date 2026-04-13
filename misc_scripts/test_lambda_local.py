from lambda_handler import lambda_handler
import shutil, os

shutil.copy('../TCCC-Trainer/00a2ceb8-83cc-4009-a3a7-8cfbc3671c43_202602188/00a2ceb8-83cc-4009-a3a7-8cfbc3671c43_202602188.csv', 'C:/tmp/')
shutil.copy('../TCCC-Trainer/00a2ceb8-83cc-4009-a3a7-8cfbc3671c43_202602188/00a2ceb8-83cc-4009-a3a7-8cfbc3671c43_202602188.json', 'C:/tmp/')

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