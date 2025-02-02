import axios from 'axios'

const url = 'http://127.0.0.1:5000/'
const ml_url = 'http://127.0.0.1:5001/'

export function authenticate(userData){
  return axios.post(url + 'login/', userData)
}

export function register(userData){
  return axios.post(url + 'register/', userData)
}

export async function getUserData(jwt){
  return await axios.get(url + 'userdata/', { headers: { token : jwt}})
}

export async function updateUserData(userData, jwt){
  return await axios.put(url + 'settings/', userData, {headers : {token : jwt}})
}

export async function getProfileData(id){
  return await axios.put(url + 'profile/')
}

export async function getExplore(){
  return await axios.put(url + 'explore/')
}

export async function getDatasets(ds_name) {
  return await axios.post(url + 'datasets/')
}

export function sendEmail(userEmail){
  return axios.post(url + 'forgotpass/', { 'email' : userEmail})
}

export function resetPass(userData, jwt){
  return axios.post(url + 'changePass/', userData, {headers : {token : jwt}})
}

export function getJobData(jwt){
  return axios.get(url + 'getJobData/', {headers : {token : jwt}})
}

export function getFinishedJobs(jwt){
  return axios.get(url + 'getFinishedJobs/', {headers : {token : jwt}})
}

export function getCurrentJobs(jwt){
  return axios.get(ml_url + 'getCurrentJobs/', {headers : {token : jwt}})
}

export async function getDatasetImgs(ds_name) {
  return await axios.post(url + 'datasetview/' + ds_name + '/')
}

export async function collectionsDatasets(project_name) {
  return await axios.post(url + 'collections/' + project_name + '/')
}

export async function newProject() {
  return await axios.post(url + 'collections/newProject/')
}

export async function getCollections() {
  return await axios.post(url + 'collections/')
}