import os
import pickle
import subprocess

password = "hunter2hunter2"
exec("print(1)")
os.system("ls /tmp")
subprocess.run("rm /etc/foo", shell=True)
data = pickle.load(open("/data/scratch/x.pkl", "rb"))
