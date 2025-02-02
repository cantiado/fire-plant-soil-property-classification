import os, glob
import shutil
import pandas as pd
from pathlib import Path
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import datetime
from flask_cors import CORS

from redis import Redis
from rq import Queue
from rq.job import Job

from functools import wraps
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
import jwt



from app import Image
from app import Dataset
from app import Upload
from app import JobRegistry
from app import User

from app import token_required

from api import bookKeeping
from api import job_callback

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///user.db"
app.config['SECRET_KEY'] = '95fd1e474cbc4b49a3286dc09cba7510'

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USERNAME'] = "pspnetcs426@gmail.com"
app.config['MAIL_PASSWORD'] = "lvzuijgmkvbsuayw"
app.config['TESTING'] = False


from app import db
db.init_app(app)
#db = SQLAlchemy(app)
#db.init_app(app)

CORS(app, resources={r"/*":{'origins':"*"}})

r = Redis(host='redis', port=6379)
queue = Queue(connection=r)


image_folder = "images"

def token_required(f):
  @wraps(f)
  def authorize(*args, **kwargs):
    token = request.headers.get('token')

    invalid_msg = {
      'message' : 'Invalid token.',
      'authenticated' : False
    }
    expired_msg = {
      'message' : 'Expired token.',
      'authenticated' : False
    }
    try:
      data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
      user = User.query.filter_by(id=data['sub']).first()
      if not user:
        raise RuntimeError('User not found')
      return f(user, *args, **kwargs)
    except ExpiredSignatureError:
      return jsonify(expired_msg), 401
    except (InvalidTokenError, Exception) as e:
      print(str(e))
      #return jsonify(invalid_msg), 401
      return jsonify({'error' : str(e)}), 401
    
  return authorize



def YOLOv5(path, job_id):
  #executes yolo prediction model on images/jobs folder...
  os.chdir(path)
  directory = 'images/' +str(job_id)

  #type checks each file in directory to verify if user uploaded images, if not error is returned and function terminates
  for filename in os.listdir(directory):
    f = os.path.join(directory, filename)
    # checking if it is a file
    if f.lower().endswith(('bmp', 'dng', 'jpeg', 'jpg', 'mpo', 'png', 'tif', 'tiff', 'webp', 'pfm')):
        print("")
    else:
      print("Error, Prediction Failed.\nUser Uploaded Incorrect File Type.")
      return 0

  print("Predicting...")
  cmd = r'python yolov5/classify/predict.py --weights yolov5/best.onnx --save-txt --source images/' + str(job_id) + r' --img 640'
  os.system(cmd)
  return 1

def shutilFunction(job_id, job_folder, path):
  #changes back to pspnet/server-side folder to append predictions.txt to csv file.
  os.chdir(path)
  prediction_ID = "labels/predictions" + str(job_id) + ".csv" #creates unique string for shutil
  shutil.move(prediction_ID, job_folder)
  shutil.rmtree(r"labels/")

def csvCreation(job_id):
  os.chdir("labels")
  #lists here are used when parsing through text files in the label directory after prediciton
  listOne = []
  listTwo = []
  split = []

  #looks for each file with the .txt extension in the labels directory
  for filename in glob.glob('*.txt'):
    with open(os.path.join(os.getcwd(), filename), 'r') as f: # opens text file in readonly mode
      textLine = f.readlines() #gets each line from an individual text file
      for x in range(5): #reads through top five predictions in each text line
        split = textLine[x].split(" ", 1) #splits the confidence interval from species classification
        predictionNumber = filename + " prediction: " + str(x) #creates new string to indicate classification order
        listOne = [split[0], split[1], predictionNumber] #adds each id to a list
        listTwo.append(listOne) #appends the list into one larger list
  
  #creates a new csv data frame containing top 5 classifications for each image
  prediction = pd.DataFrame(listTwo, columns=['CONFIDENCE_INTERVAL', 'SPECIES', 'PICTURE_ID'])  
  prediction.insert(3, "MODEL: YOLOv5", " ")
  prediction_ID = "predictions" + str(job_id) + ".csv" 
  prediction.to_csv(prediction_ID) #converts the dataframe to a csv

@app.route("/identify/", methods=["GET", "POST"])
def identify():
  if request.method == "GET":
    public_ds = db.session.query(Dataset.name).filter(Dataset.visibility=='public').all()
    datasets = [ds_query[0] for ds_query in public_ds]
    return jsonify({'datasets' : datasets}), 200

  # files = request.files.to_dict(flat=False)["image-input"]
  files = request.files.to_dict(flat=False)["images"]
  form_info = request.form.to_dict()
  user_id = form_info['user-id']
  dataset_name = form_info['dataset-name']
  dataset_description = form_info['dataset-notes']
  upload_notes = None if dataset_description == "" else dataset_description
  dataset_description = upload_notes # placeholder for dataset info
  dataset_location = form_info['dataset-geoloc']
  dataset_location = None if dataset_location == "" else dataset_location
  visibility = form_info['visibility']
  timestamp = form_info['timestamp']
  new_upload = Upload(user_id, dataset_name, upload_notes, timestamp, len(files))
  db.session.add(new_upload)
  db.session.commit()

  job_id = db.session.query(Upload.id).order_by(Upload.id.desc()).first()[0]
  
  # form_info["dataset-name"]: dataset name
  # form_info["dataset-notes"]: dataset notes
  # form_info["dataset-geoloc"]: dataset geolocation
  # form_info["visibility"]: {"public", "private"}
  # form_info["user-id"]: user id
  

  job_folder = os.path.join(image_folder, str(job_id)) 
  os.makedirs(job_folder)
  numImages = 0
  for i, file in enumerate(files):
    file.save(os.path.join(job_folder, file.filename))
    new_image = Image(os.path.join(job_folder, file.filename), user_id, 
                      job_id, dataset_name, location=dataset_location)
    db.session.add(new_image)
    
    numImages = numImages + 1
    # save file paths to image database
  upload_img_size = os.path.getsize(job_folder) / 100
  # query to get data from previous entries of the dataset
  ds_data = db.session.query(Dataset.num_images, Dataset.num_uploads,
                             Dataset.size, Dataset.id).filter_by(name = dataset_name). \
                              order_by(Dataset.id.desc()).first()
  total_images = numImages
  total_size = upload_img_size
  total_uploads = 1
  if ds_data is not None: # update existing entry
    db.session.query(Dataset).filter(Dataset.id==ds_data[3]) \
      .update({Dataset.num_images : total_images+ds_data[0],
               Dataset.num_uploads : ds_data[1]+1,
               Dataset.size : total_size+ds_data[2]}, synchronize_session=False)
    # total_images += ds_data[0]
    # total_uploads += ds_data[1]
    # total_size += ds_data[2]
  else:
    new_dataset = Dataset(dataset_name, dataset_description, 
                          dataset_location, visibility, total_images,
                          total_uploads, total_size)
    db.session.add(new_dataset)
  db.session.commit()
  # new_dataset.numimages = numImages
  #commands here give global environment path to project for deployment on any machine
  FILE = Path(__file__).resolve()
  path = FILE.parents[0]

  print("Predicting...")
  new_job = queue.enqueue(bookKeeping, args=(job_id, path, job_folder), job_id=str(job_id), on_success=job_callback)
  added_job = JobRegistry(new_job.id,
                          user_id,
                          dataset_name,
                          dataset_description,
                          dataset_location,
                          'Yolov5',
                          numImages,
                          new_job.enqueued_at)
  db.session.add(added_job)

  #fill in upload table using new_job attributes
  #the finishtime should be set to null


  # db.session.add(new_dataset)
  db.session.commit()

  return "Success!"


@app.route('/getCurrentJobs/', methods = ['GET'])
@token_required
def getCurrentJobs(user):
  
  current_jobs = JobRegistry.query.filter_by(finishtime = None).filter_by(uploader_id=user.id).all()
  jobs_data = []

  for job in current_jobs:
    redis_job = Job.fetch(str(job.job_id), connection=r)

    print(redis_job.get_position())

    single_data = {
      'id' : job.job_id,
      'datasetName' : job.dataset,
      'datasetNotes' : job.uploadNote,
      'datasetGeoloc' : job.geolocation,
      'visibility' : 'yes',
      'model' : job.model,
      'numImages' : job.numimages,
      'start' : job.starttime,
      'eta' : str('executing' if redis_job.get_position() == None else redis_job.get_position() + 1)
    }
    jobs_data.append(single_data)
  return jsonify(jobs_data), 200

if __name__ == "__main__":
  app.run(port=5001, debug=True, host='0.0.0.0')