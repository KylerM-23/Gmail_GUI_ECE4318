import os
# Gmail API utils
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
# for encoding/decoding messages in base64
from base64 import urlsafe_b64decode, urlsafe_b64encode
# for dealing with attachement MIME types
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from mimetypes import guess_type as guess_mime_type
import base64  
from bs4 import BeautifulSoup

class email_handler:
    SCOPES = ['https://mail.google.com/']
    myemail = ''
    service = None
    
    def __init__(self):
        self.service = self.gmail_authenticate() #get the Gmail API service
        self.myemail = self.service.users().getProfile(userId = 'me').execute()['emailAddress'] #get user email
        
    def gmail_authenticate(self):
        creds = None
        # The file token.json stores the user authentication token.
        # If there is an existing token, load it.
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.SCOPES)
        # If a token does not exist, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for next time
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
                
        service = build('gmail', 'v1', credentials=creds) #create a gmail service
        return service

    def add_attachment(self, message, filename):
        content_type, encoding = guess_mime_type(filename)          #determine file type
        if content_type is None or encoding is not None:            #default
            content_type = 'application/octet-stream'
        main_type, sub_type = content_type.split('/', 1)            #seperate types
        fp = open(filename, 'rb')                                   #open file and if the file is...
        if main_type == 'text':
            msg = MIMEText(fp.read().decode(), _subtype=sub_type)
        elif main_type == 'image':
            msg = MIMEImage(fp.read(), _subtype=sub_type)
        elif main_type == 'audio':
            msg = MIMEAudio(fp.read(), _subtype=sub_type)
        else:                                                       #default
            msg = MIMEBase(main_type, sub_type)
            msg.set_payload(fp.read())
        fp.close()                                                  #close file when done
        filename = os.path.basename(filename)                       #get the file name
        msg.add_header('Content-Disposition', 'attachment', filename=filename) #add header for attachment
        message.attach(msg)                                         #attach to message

    def createEmailMessage(self, message_dict, attachments):
        message = None #placeholder
        if attachments == None:                         #if no attachments
            message = MIMEText(message_dict['body'])    #create the message with the body
        else:                                           #if there are attachments
            message = MIMEMultipart()                   #set the body as a multiplart file
            message.attach(MIMEText(message_dict['body'])) #attach body to the email
            for filename in attachments:                #for each attachment
                self.add_attachment(message, filename)  #add to the message
        
        message['to'] = message_dict['to']              #set the to
        message['from'] = self.myemail                  #set the from
        message['subject'] = message_dict['subject']    #set the subject
        message['cc'] = message_dict['cc']              #set the cc
        message['bcc'] = message_dict['bcc']            #set the bcc

        raw_message = {'raw': urlsafe_b64encode(message.as_bytes()).decode()} #encode message
        return raw_message
    
    def send_message(self, message_dict, attachments = None):
        self.service.users().messages().send(userId="me",
        body= self.createEmailMessage(message_dict, attachments)).execute()
        
    def cleanTxt(self, txt): #helper function to remove excess whitespace
        cleantxt = ''
        firstChar = False

        for c in txt:
            if firstChar:
                cleantxt += c
            else:
                if c != ' ':
                    cleantxt += c
                    firstChar = True
        return cleantxt

    def get_size_format(self, b, factor=1024, suffix="B"):  #scale the bytes to a common unit
        for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:#Byte, Kilo, Mega...
            if b < factor:
                return f"{b:.2f}{unit}{suffix}"
            b /= factor
        return f"{b:.2f}Y{suffix}"                          #Yottabyte

    def parse_parts(self, parts, folder_name, message):
        if parts:
            for part in parts:
                filename = part.get("filename")
                mimeType = part.get("mimeType")
                body = part.get("body")
                data = body.get("data")
                file_size = body.get("size")
                part_headers = part.get("headers")
                if part.get("parts"):
                    # recursively call this function when we see that a part
                    # has parts inside
                    self.parse_parts(part.get("parts"), folder_name, message)
                if mimeType == "text/plain":
                    # if the email part is text plain
                    if data:
                        text = urlsafe_b64decode(data).decode()
                        if not filename:
                            filename = "body.txt"
                        filepath = os.path.join(folder_name, filename)
                        with open(filepath, "w") as f:
                            f.write(text)

                elif mimeType == "text/html":
                    # if the email part is an HTML content
                    # save the HTML file and optionally open it in the browser
                    if not filename:
                        filename = "index.html"
                    filepath = os.path.join(folder_name, filename)
                    with open(filepath, "wb") as f:
                        f.write(urlsafe_b64decode(data))
                else:
                    # attachment other than a plain text or HTML
                    for part_header in part_headers:
                        part_header_name = part_header.get("name")
                        part_header_value = part_header.get("value")
                        if part_header_name == "Content-Disposition":
                            if "attachment" in part_header_value:
                                # we get the attachment ID 
                                # and make another request to get the attachment itself
                                print("Saving the file:", filename, "size:", self.get_size_format(file_size))
                                attachment_id = body.get("attachmentId")
                                attachment = self.service.users().messages() \
                                            .attachments().get(id=attachment_id, userId='me', messageId=message['id']).execute()
                                data = attachment.get("data")
                                filepath = os.path.join(folder_name, filename)
                                if data:
                                    with open(filepath, "wb") as f:
                                        f.write(urlsafe_b64decode(data))

    def getMessages(self, labels = ['INBOX'], amount = 10):                                
        msgList = self.service.users().messages().list(userId='me',
                labelIds = labels, maxResults = amount).execute() #get amount emails with the labels specified
        messages = msgList['messages']                          #retrieve the messages
        emails = []                                             #list for email in dictionary formatpayload = email['payload']
        for msg in messages:                                    #for the messages, get the email information
            email = self.service.users().messages().get(userId = 'me', id=msg['id'], format='full').execute()
            payload = email['payload']
            temp_email = {                                      #default values
                'from name': 'Missing Sender', 
                'from email': 'Missing Email', 
                'to': 'N/A',
                'cc': 'N/A',
                'subject': 'Subject N/A', 
                'date': 'No Date',
                'snippet': ' ', 
                'body': ' ',
                'id': msg['id'],
                'parts': payload.get("parts")
            }
            
            for head in email['payload']['headers']:            #for all headers
                name = head.get("name").lower()                 #lowercase everything, sometimes gmail returns captial
                if (name == 'from'):                            #from is in the format Name <name123@gmail.com> or name123@gmail.com
                    value = head.get('value')                   #get the name and email
                    if '<' in value:                            #if the name is there
                        from_info = value.split(" <")           #split into strings to clean up
                        if (len(from_info) > 1):                #if split into two
                            from_info[1] = from_info[1][0:-1]   #get the email
                        else:                                   #both values are the email for the name and email    
                            from_info*=2
                    else:
                        from_info = [value, value]
                    temp_email['from name'] = self.cleanTxt(from_info[0].replace('"', ' ')) #remove extrawhitespace for the name
                    temp_email['from email'] = from_info[1]     #save the email seperately
                elif name.lower() == "to":
                    temp_email['to'] = head.get('value').replace('<', '').replace('>', '')   #save it
                elif name.lower() == "cc":
                    temp_email['cc'] = head.get('value').replace('<', '').replace('>', '')  #save it
                elif(name == 'subject'):                        #if it is a subject
                    temp_email['subject'] = head.get('value')   #save it
                
                elif (name == 'date'):                          #date formatted as Weekday, Month Day Year time timezone
                    temp_date = head.get('value').split(' ')    #split into components to make Month, Day, Year string
                    if (temp_date[0] in ['Mon,', 'Tue,', 'Wed,','Thu,','Fri,','Sat,','Sun,']): #if weekday included
                        temp_email['date'] =  str(int(temp_date[1])) + ' ' + temp_date[2] + ' ' + temp_date[3] #create new string
                    else:
                        temp_email['date'] =  str(int(temp_date[0])) + ' ' + temp_date[1] + ' ' + temp_date[2] #create new string

            temp_email['snippet'] =  email['snippet']           #get email snippet
            try:
                parts = payload.get('parts')[0]
                data = parts['body']['data']
                data = data.replace("-","+").replace("_","/")
                decoded_data = base64.b64decode(data)
                temp_email['body'] = decoded_data.decode()
            except:
                temp_email['body'] =  email['snippet']

            emails.append(temp_email)                           #add to email list
        return emails                                           #return emails
        




