import subprocess


datasets = ['Tmall', 'Gowalla', 'Nowplaying'] #'Tmall', 'Gowalla', 'Nowplaying'
for data in datasets:
    subprocess.run(["python", "./main_model_exp30.py", "--dataset", data, "--validation", "--num-workers", "8"])