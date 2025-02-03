import os
import re
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
from pymongo import MongoClient
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from bson import ObjectId
from dotenv import load_dotenv
from pymongo.errors import ConnectionFailure
import pymongo

load_dotenv()


def clean_response_text(text):
    clean_text = re.sub(r'\*+', '', text)
    clean_text = re.sub(r'\<.*?\>', '', clean_text)
    clean_text = clean_text.replace('\n', ' ')
    clean_text = clean_text.strip()
    return clean_text


OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
MONGODB_URI = os.getenv('MONGODB_URI')
TOKEN = os.getenv('TOKEN')
DATABASE_NAME = os.getenv('DATABASE_NAME')
CORS_URL= os.getenv('CORS_URL')

client = MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
project_collection = "project"
lead_collection = "Lead"
user_collection = "users"
org_collection = "organisation"
task_collection = "task"
leadtask_collection = "leadTask"
opentask_collection = "opentask"
database = client[DATABASE_NAME]

conversation_history = {}


class QueryRequest(BaseModel):
    question: str
    org_id: str
    user_id: str
    
    
    
class mailRequest(BaseModel):
    email_info: str
        
    


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/query/")
async def query_rag_system(request: QueryRequest):
    try:
        context = {}
        org_id = request.org_id
        user_id = request.user_id
        project_id = None
        lead_id = None
        task_id = None
        taskName = None
        casual_greetings = ["Hello", "hello", "Hi", "hi", "hey", "greetings",
                            "good morning", "good afternoon", "good evening", "good day", "hey there"]

        # If the user's question contains any casual greeting
        if any(greeting in request.question.lower() for greeting in casual_greetings):
            context = {
                "role": "system",
                "content": "You are a helpful assistant that provides information about projects, leads, and tasks in a company crm management system. You will respond in a concise and clear manner."
            }
        
        check_org = db[org_collection].find_one({"_id": ObjectId(org_id)})
        if not check_org:
            raise HTTPException(
                status_code=404, detail="Organisation not found")

        # Check user
        check_user = db[user_collection].find_one(
            {"_id": ObjectId(user_id), "organization": org_id})
        if not check_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check for project name, lead name, and user name in the request

        if any(phrase in request.question.lower() for phrase in ["entire projects", "all projects", "whole projects", "all project"]):
            project_id = '00000000000'
        else:
            match = re.search(
                r' of project ([\w\s]+)', request.question, re.IGNORECASE)
            project_name = match.group(1) if match else None

        if any(phrase in request.question.lower() for phrase in ["entire leads", "all leads",  "all lead", "whole leads"]):
            lead_id = '111111'
        else:
            match = re.search(r'of lead ([\w\s]+)',
                              request.question, re.IGNORECASE)
            lead_name = match.group(1) if match else None
        
        if any(phrase in request.question.lower() for phrase in ["entire tasks", "all tasks", "all task", "whole tasks"]):
            task_id = '222222222'
        else:
            match = re.search(r'task\s+([a-zA-Z\s]+?)(?=\s+of|\s*$)',
                              request.question, re.IGNORECASE)
            taskName = match.group(1).strip() if match else None

        match = re.search(r'user ([\w\s]+)', request.question, re.IGNORECASE)
        user_name = match.group(1) if match else None
        # Check user role
        
        # print(project_name, lead_name)       
        role = check_user.get('role')
        if role in ['ADMIN', 'SUPERADMIN']:
            # Handle projects
            if project_id == '00000000000':
                projects = list(
                    db[project_collection].find({"org_id": org_id}))
                project_list = [
                    {
                        'project_name': project.get('project_name'),
                        'client_info': project.get('client'),
                        'phase': project.get('project_status'),
                    }
                    for project in projects
                ]
                context['projects'] = project_list
            elif project_name:
                if task_id == '222222222':
                    if project_name:
                        project_details = db[project_collection].find_one(
                            {"project_name": project_name, "org_id": org_id})
                        if project_details:
                            project_id = project_details.get("project_id")
                            tasks = list(
                                db[task_collection].find({"project_id": project_id}))
                            task_list = [
                                {
                                    'task_name': task.get('task_name'),
                                    'task_assignee': task.get('task_assignee'),
                                    'reporter': task.get('reporter'),
                                    'task_status': task.get('task_status'),
                                    'task_priority': task.get('task_priority'),
                                    'task_createdOn': task.get('task_createdOn'),
                                    'estimated_task_start_date': task.get('estimated_task_start_date'),
                                    'estimated_task_end_date': task.get('estimated_task_end_date'),
                                }
                                for task in tasks
                            ]
                            context['tasks'] = task_list
                        else:
                            context = {"message": "project not found"}
                    else:
                        context = {"message": "project not found"}

                elif project_name and taskName:
                    project_details = db[project_collection].find_one(
                        {"project_name": project_name, "org_id": org_id})

                    if project_details:
                        project_id = project_details.get("project_id")

                        task_details = db[task_collection].find_one(
                            {"project_id": project_id, "task_name": taskName})
                        
                        if task_details:
                            task_id = task_details.get("task_id")
                            # task_info = {k: v for k, v in task_details.items(
                            # ) if k not in ['_id', 'task_id', 'org_id', 'fileId']}
                            context.update(task_details)
                        else:
                            context = {"message": "task not found"}

                    else:
                        context = {"message": "project not found"}
                elif project_name:
                    project_details = db[project_collection].find_one(
                        {"project_name": project_name, "org_id": org_id})
                    if project_details:
                        project_id = project_details.get("project_id")
                        project_info = {k: v for k, v in project_details.items(
                        ) if k not in ['_id', 'project_id', 'org_id', 'fileId']}
                        project_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                            {'data.projectData.project_id': project_details.get('project_id'), "organization": org_id})]
                        context.update(project_info)
                    else:
                        context = {"message": "project not found"}

            # Handle leads
            elif lead_id == '111111':
                
                leads = list(db[lead_collection].find({"org_id": org_id}))
                lead_list = [
                    {k: v for k, v in lead.items() if k not in [
                        '_id', 'lead_id', 'org_id', 'fileId']}
                    for lead in leads
                ]
                context['leads'] = lead_list
            elif lead_name:    
                if task_id == '222222222':
                    if lead_name:
                        lead_details = db[lead_collection].find_one(
                            {"name": lead_name, "org_id": org_id})
                        if lead_details:
                            lead_id = lead_details.get("lead_id")
                            tasks = list(
                                db[leadtask_collection].find({"lead_id": lead_id}))
                            task_list = [
                                {
                                    'task_name': task.get('task_name'),
                                    'task_assignee': task.get('task_assignee'),
                                    'reporter': task.get('reporter'),
                                    'task_status': task.get('task_status'),
                                    'task_priority': task.get('task_priority'),
                                    'task_createdOn': task.get('task_createdOn'),
                                    'estimated_task_start_date': task.get('estimated_task_start_date'),
                                    'estimated_task_end_date': task.get('estimated_task_end_date'),
                                }
                                for task in tasks
                            ]
                            context['tasks'] = task_list
                        else:
                            context = {"message": "lead not found"}
                    else:
                        context = {"message": "lead not found"}

                elif lead_name and taskName:
                    lead_details = db[lead_collection].find_one(
                        {"name": lead_name, "org_id": org_id})

                    if lead_details:
                        lead_id = lead_details.get("lead_id")

                        task_details = db[leadtask_collection].find_one(
                            {"lead_id": lead_id, "task_name": taskName})
                        
                        if task_details:
                            task_id = task_details.get("task_id")
                            # task_info = {k: v for k, v in task_details.items(
                            # ) if k not in ['_id', 'task_id', 'org_id', 'fileId']}
                            context.update(task_details)
                        else:
                            context = {"message": "task not found"}

                    else:
                        context = {"message": "lead not found"}
                elif lead_name:
                    lead_details = db[lead_collection].find_one(
                        {"name": lead_name, "org_id": org_id})
                    if lead_details:
                        lead_id = lead_details.get("lead_id")
                        lead_info = {k: v for k, v in lead_details.items(
                        ) if k not in ['_id', 'lead_id', 'org_id', 'fileId']}
                        lead_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                            {'data.leadData.lead_id': lead_details.get('lead_id'), "organization": org_id})]
                        context.update(lead_info)
                    else:
                        context = {"message": "lead not found"}    
            
            if user_name:
                user_details = db[user_collection].find_one(
                    {"username": user_name, "organization": org_id})
                if user_details:
                    user_info = {k: v for k, v in user_details.items() if k not in [
                        '_id', 'org_id', 'organization', 'password', 'data', 'refreshToken', 'userProfile']}
                    org_details = db[org_collection].find_one(
                        {"_id": ObjectId(org_id)})
                    if org_details:
                        user_info['organisation_name'] = org_details.get(
                            'organization')
                    context.update(user_info)
                else:
                    raise HTTPException(
                        status_code=404, detail="User not found.")

        elif role in ['Senior Architect']:
            # Similar logic as above for Senior Architect
            if project_id == '00000000000':
                projects = list(
                    db[project_collection].find({"org_id": org_id}))
                project_list = [
                    {
                        'project_name': project.get('project_name'),
                        'client_info': project.get('client'),
                        'phase': project.get('project_status'),
                    }
                    for project in projects
                ]
                context['projects'] = project_list
            elif project_name:
                if task_id == '222222222':
                    if project_name:
                        project_details = db[project_collection].find_one(
                            {"project_name": project_name, "org_id": org_id})
                        if project_details:
                            project_id = project_details.get("project_id")
                            tasks = list(
                                db[task_collection].find({"project_id": project_id}))
                            task_list = [
                                {
                                    'task_name': task.get('task_name'),
                                    'task_assignee': task.get('task_assignee'),
                                    'reporter': task.get('reporter'),
                                    'task_status': task.get('task_status'),
                                    'task_priority': task.get('task_priority'),
                                    'task_createdOn': task.get('task_createdOn'),
                                    'estimated_task_start_date': task.get('estimated_task_start_date'),
                                    'estimated_task_end_date': task.get('estimated_task_end_date'),
                                }
                                for task in tasks
                            ]
                            context['tasks'] = task_list
                        else:
                            context = {"message": "project not found"}
                    else:
                        context = {"message": "project not found"}

                elif project_name and taskName:
                    project_details = db[project_collection].find_one(
                        {"project_name": project_name, "org_id": org_id})

                    if project_details:
                        project_id = project_details.get("project_id")

                        task_details = db[task_collection].find_one(
                            {"project_id": project_id, "task_name": taskName})
                        print(task_details)
                        if task_details:
                            task_id = task_details.get("task_id")
                            # task_info = {k: v for k, v in task_details.items(
                            # ) if k not in ['_id', 'task_id', 'org_id', 'fileId']}
                            context.update(task_details)
                        else:
                            context = {"message": "task not found"}

                    else:
                        context = {"message": "project not found"}
                elif project_name:
                    project_details = db[project_collection].find_one(
                        {"project_name": project_name, "org_id": org_id})
                    if project_details:
                        project_id = project_details.get("project_id")
                        project_info = {k: v for k, v in project_details.items(
                        ) if k not in ['_id', 'project_id', 'org_id', 'fileId']}
                        project_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                            {'data.projectData.project_id': project_details.get('project_id'), "organization": org_id})]
                        context.update(project_info)
                    else:
                        context = {"message": "project not found"}

            # Handle leads
            elif lead_id == '111111':
                
                leads = list(db[lead_collection].find({"org_id": org_id}))
                lead_list = [
                    {k: v for k, v in lead.items() if k not in [
                        '_id', 'lead_id', 'org_id', 'fileId']}
                    for lead in leads
                ]
                context['leads'] = lead_list
            elif lead_name:    
                if task_id == '222222222':
                    if lead_name:
                        lead_details = db[lead_collection].find_one(
                            {"name": lead_name, "org_id": org_id})
                        if lead_details:
                            lead_id = lead_details.get("lead_id")
                            tasks = list(
                                db[leadtask_collection].find({"lead_id": lead_id}))
                            task_list = [
                                {
                                    'task_name': task.get('task_name'),
                                    'task_assignee': task.get('task_assignee'),
                                    'reporter': task.get('reporter'),
                                    'task_status': task.get('task_status'),
                                    'task_priority': task.get('task_priority'),
                                    'task_createdOn': task.get('task_createdOn'),
                                    'estimated_task_start_date': task.get('estimated_task_start_date'),
                                    'estimated_task_end_date': task.get('estimated_task_end_date'),
                                }
                                for task in tasks
                            ]
                            context['tasks'] = task_list
                        else:
                            context = {"message": "lead not found"}
                    else:
                        context = {"message": "lead not found"}

                elif lead_name and taskName:
                    lead_details = db[lead_collection].find_one(
                        {"name": lead_name, "org_id": org_id})

                    if lead_details:
                        lead_id = lead_details.get("lead_id")

                        task_details = db[leadtask_collection].find_one(
                            {"lead_id": lead_id, "task_name": taskName})
                        print(task_details)
                        if task_details:
                            task_id = task_details.get("task_id")
                            # task_info = {k: v for k, v in task_details.items(
                            # ) if k not in ['_id', 'task_id', 'org_id', 'fileId']}
                            context.update(task_details)
                        else:
                            context = {"message": "task not found"}

                    else:
                        context = {"message": "lead not found"}
                elif lead_name:
                    lead_details = db[lead_collection].find_one(
                        {"name": lead_name, "org_id": org_id})
                    if lead_details:
                        lead_id = lead_details.get("lead_id")
                        lead_info = {k: v for k, v in lead_details.items(
                        ) if k not in ['_id', 'lead_id', 'org_id', 'fileId']}
                        lead_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                            {'data.leadData.lead_id': lead_details.get('lead_id'), "organization": org_id})]
                        context.update(lead_info)
                    else:
                        context = {"message": "lead not found"}    
            
        else:
            # For other roles, check access

            find_project = db[project_collection].find_one(
                {"project_name": project_name, "org_id": org_id})
            find_lead = db[lead_collection].find_one(
                {"name": lead_name, "org_id": org_id})
            if find_project:
                project_id = find_project.get("project_id")
                check_user_access = db[user_collection].find_one({"_id": ObjectId(
                    user_id), "organization": org_id, "data.projectData.project_id": project_id})
                if check_user_access:
                    if task_id == '222222222':
                        if project_name:
                            project_details = db[project_collection].find_one(
                                {"project_name": project_name, "org_id": org_id})
                            if project_details:
                                project_id = project_details.get("project_id")
                                tasks = list(
                                    db[task_collection].find({"project_id": project_id}))
                                task_list = [
                                    {
                                        'task_name': task.get('task_name'),
                                        'task_assignee': task.get('task_assignee'),
                                        'reporter': task.get('reporter'),
                                        'task_status': task.get('task_status'),
                                        'task_priority': task.get('task_priority'),
                                        'task_createdOn': task.get('task_createdOn'),
                                        'estimated_task_start_date': task.get('estimated_task_start_date'),
                                        'estimated_task_end_date': task.get('estimated_task_end_date'),
                                    }
                                    for task in tasks
                                ]
                                context['tasks'] = task_list
                            else:
                                context = {"message": "project not found"}
                        else:
                            context = {"message": "project not found"}
                    project_info = {k: v for k, v in find_project.items() if k not in [
                        '_id', 'project_id', 'org_id']}
                    project_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                        {'data.projectData.project_id': project_id, "organization": org_id})]
                    context = project_info
                else:
                    context = {
                        "message": "You do not have access to get this project details."}
            elif find_lead:
                lead_id = find_lead.get("lead_id")
                check_user_access = db[user_collection].find_one({"_id": ObjectId(
                    user_id), "organization": org_id, "data.leadData.lead_id": lead_id})
                if check_user_access:
                    if task_id == '222222222':
                        if lead_name:
                            lead_details = db[lead_collection].find_one(
                                {"name": lead_name, "org_id": org_id})
                            if lead_details:
                                lead_id = lead_details.get("lead_id")
                                tasks = list(
                                    db[leadtask_collection].find({"lead_id": lead_id}))
                                task_list = [
                                    {
                                        'task_name': task.get('task_name'),
                                        'task_assignee': task.get('task_assignee'),
                                        'reporter': task.get('reporter'),
                                        'task_status': task.get('task_status'),
                                        'task_priority': task.get('task_priority'),
                                        'task_createdOn': task.get('task_createdOn'),
                                        'estimated_task_start_date': task.get('estimated_task_start_date'),
                                        'estimated_task_end_date': task.get('estimated_task_end_date'),
                                    }
                                    for task in tasks
                                ]
                                context['tasks'] = task_list
                            else:
                                context = {"message": "lead not found"}
                        else:
                            context = {"message": "lead not found"}
                    lead_info = {k: v for k, v in find_lead.items() if k not in [
                        '_id', 'lead_id', 'org_id']}
                    lead_info['assignees'] = [assignee['username'] for assignee in db[user_collection].find(
                        {'data.leadData.lead_id': lead_id, "organization": org_id})]
                    context = lead_info
                else:
                    context = {
                        "message": "You do not have access to this lead."}
            else:
                context = {"message": "You do not have access to get details."}
            conversation_history[user_id] = model_answer
        # print(context)
       
        if taskName:
            task_details = db[opentask_collection].find_one(
                {"task_name": taskName, "org_id": org_id})
            
            if task_details:
                task_id = task_details.get('task_id')
                context['task'] = task_details
        if task_id == '222222222' and project_name ==None and lead_name ==None:
            tasks_details = list(db[opentask_collection].find({"org_id": org_id}))
            if tasks_details:
                 task_list = [
                                {
                                    'task_name': task.get('task_name'),
                                    'task_assignee': task.get('task_assignee'),
                                    'reporter': task.get('reporter'),
                                    'task_status': task.get('task_status'),
                                    'task_priority': task.get('task_priority'),
                                    'task_createdOn': task.get('task_createdOn'),
                                    'estimated_task_start_date': task.get('estimated_task_start_date'),
                                    'estimated_task_end_date': task.get('estimated_task_end_date'),
                                }
                                for task in tasks_details
                            ]
                 context['tasks'] = task_list
            else:
                context = {"message": "No tasks found."}
        
            
        if not context:  # If no specific conditions match, use the context from the last answer
            previous_answer = conversation_history.get(user_id)
            if previous_answer:
                context = previous_answer
            else:
                context = {
                    'message': "No specific project, lead, or task found. Here is the context from previous answer."}
        conversation_history[user_id] = context

        # Prepare the request to the Gemini API
        # gemini_url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent'
        initializ_url = 'https://colonelz.prod.devai.initz.run/initializ/v1/ai/chat'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {TOKEN}'
        }
        data = {

            "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that provides accurate answers to questions based on the provided context. Never send the details directly in the response. Always summarize or provide relevant information as needed, without raw data."
                },
                {
                    "role": "user",
                    "content": f"Summarize the following details '{request.question}' and the info: {context}.",
                }
            ],
            "max_tokens": 5000,
            "temperature": 0.7,
            # "stream": False,
            "stream": True

        }

        # Call the Gemini API
        response = requests.post(
            initializ_url, headers=headers, json=data)
        if response.status_code == 200:
            print("Response Status: 200 OK")
        else:
            print(f"Error: {response.status_code}")
            # Print the raw content of the error response
            print("Error Response Content:")
            print(response.text)

        # Streaming response generator
        async def event_generator(project_id, lead_id, task_id):
            projectId = True
            leadId = True
            taskId = True
            for chunk in response.iter_lines(decode_unicode=True):
                if chunk:
                    yield f"{chunk.strip()}\n\n"
                    # await asyncio.sleep(1)
                    if project_id and task_id:
                        if taskId:
                            yield f"data: task_id:{task_id}\n\n"
                            taskId = False
                        if projectId:
                            yield f"data: project_id:{project_id}\n\n"
                            projectId = False
 
                    elif lead_id and task_id:
                        if taskId:
                            yield f"data: task_id:{task_id}\n\n"
                            taskId = False
                        if leadId:
                            yield f"data: lead_id:{lead_id}\n\n"
                            leadId = False
                    elif project_id:
                        if projectId:
                            yield f"data: project_id:{project_id}\n\n"
                            projectId = False
                    elif lead_id:
                        if leadId:
                            yield f"data: lead_id:{lead_id}\n\n"
                            leadId = False
                    elif task_id:
                        if taskId:
                            yield f"data: task_id:{task_id}\n\n"
                            taskId = False

        return StreamingResponse(event_generator(project_id, lead_id, task_id), media_type="text/event-stream")

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def check_mongo_connection():
    try:
        # Try to get server info
        client.admin.command('ping')
        client.server_info()  # This will raise an exception if the connection is not successful
        print("MongoDB is connected successfully.")
        return True
    except ConnectionFailure as e:
        print("Failed to connect to MongoDB.")
        print(str(e))
        return False

@app.post("/mail-gen")
async def mail_gen(request: mailRequest):
    try:
    
    # Your code here
                initializ_url = 'https://colonelz.prod.devai.initz.run/initializ/v1/ai/chat'
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {TOKEN}'
                }
                data = {

                    "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
                    "messages": [
                        {
                            "role": "system",
                            "content": """
                            Welcome to the Email Template Generator! To help create an accurate email, please provide the following: 1) Email Type (e.g., Formal, Informal, Request, Apology), 2) Recipient's Role (e.g., Manager, Customer, Client), 3) Purpose of the email (e.g., Confirming an appointment, Asking for information), 4) Key Points/Message (specific details or main ideas you want to communicate), 5) Tone/Style (e.g., Professional, Friendly, Polite), 6) Additional Info (e.g., deadlines, context, or any special requests). Once you provide these, we’ll generate a tailored email template for you.
                            """
                        },
                        {
                            "role": "user",
                            "content": f"  Give email template for {request.email_info}.",
                        }
                    ],
                    "max_tokens": 5000,
                    "temperature": 0.7,
                    "stream": False,
                    # "stream": True

                }

                # Call the Gemini API
                response = requests.post(
                    initializ_url, headers=headers, json=data)
                if response.status_code == 200:
                    print("Response Status: 200 OK")
                else:
                    print(f"Error: {response.status_code}")
                    # Print the raw content of the error response
                    print("Error Response Content:")
                    print(response.text)

                # Streaming response generator
                async def event_generator():
                    for chunk in response.iter_lines(decode_unicode=True):
                        if chunk:
                            yield f"{chunk.strip()}\n\n"
                            await asyncio.sleep(1)
                return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
if __name__ == "__main__":
    if check_mongo_connection():
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8005)
    else:
        print("Exiting due to MongoDB connection failure.")
