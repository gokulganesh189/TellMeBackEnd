import os
import re
import traceback
import boto3
import numpy as np
from datetime import datetime
from pydub import AudioSegment
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.core.paginator import Paginator
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from api.serializers import RegisterSerializer, LoginSerializer
from rest_framework.response import Response
from rest_framework import status
from api.tasks import email_task
from api.authentication import JWTAuthentication, IsAdminUser
from api.models import (DailyQuestions, UserStreak, QuestionLike, Reactions, ReactionLike)
from api.services import aws_services
from api.common import constants
from TellMe import py_jwt_token


class AddReactionTest(APIView):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)
    
    def is_valid_extension_combination(self, file_name):
        # Check for suspicious combinations like .php.png, .html.svg, etc.

        allowed_extensions = ['jpeg', 'jpg', 'png', 'bmp', 'tiff', 'svg', 'webp', 'heic', 'heif',
                            'm4a', 'wav', 'mp3', 'wma', 'aac', 'mp4', 'mov', 'mkv', 'avi', 'wmv',
                            'flv', 'webm', 'mpeg', '3gp', '3g2', 'm4v', 'pdf', 'doc', 'docx', 'xls',
                            'xlsx', 'ppt', 'pptx', 'txt', 'csv']

        base_filename, file_ext = os.path.splitext(file_name.lower())
        file_ext = file_ext[1:]
        if file_ext not in allowed_extensions:
            return True

        # Ensure the base filename doesn't end with a suspicious second extension
        last_dot_index = base_filename.rfind('.')
        if last_dot_index != -1:
            potential_extension = base_filename[last_dot_index + 1:]
            if potential_extension in allowed_extensions:
                return True

        return False
    
    def aws_initilization(self):
        aws_keys = aws_services.get_external_credentials('aws_s3')
        aws_bucket = aws_keys['AWS_BUCKET']
        aws_access_key_id = aws_keys['AWS_ACCESS_KEY_ID']
        aws_secret_access_key = aws_keys['AWS_SECRET_ACCESS_KEY']
        aws_region = aws_keys['REGION']
        return aws_bucket, aws_access_key_id, aws_secret_access_key, aws_region
    
    def generate_waveform(self, audio_path, sample_count=40):
        try:
            audio = AudioSegment.from_file(audio_path)
            samples = np.array(audio.get_array_of_samples())
            if audio.channels == 2:
                samples = samples.reshape((-1, 2)).mean(axis=1)

            chunk_size = max(1, len(samples) // sample_count)
            waveform = [float(np.abs(samples[i:i + chunk_size]).mean()) for i in range(0, len(samples), chunk_size)]
            max_val = max(waveform) or 1
            return [round(val / max_val, 2) for val in waveform]
        except Exception as e:
            print("Waveform generation error:", e)
            return None
    
    def post(self, request):
        user = request.user
        file_content = request.FILES.get('file_content')
        time_stamp = request.data.get('time_stamp', None)
        is_recorded = request.data.get("is_recorded") 
        question_id = request.data.get("question_id")
        is_reaction = request.data.get('is_reaction')
        
        file_name = file_content.name
        file_type = file_content.content_type
        filename, file_extension = os.path.splitext(file_name)
        file_extension = file_extension.lower().strip()
        docType = 'Text'
        
        if not file_content:
            return Response({'status': constants.FAILED_STATUS, 'message': 'No file found'}, status=400)
        # Check for multiple extensions, e.g., .php.png, .svg.xlsx
        if self.is_valid_extension_combination(file_name):
            return Response({'status': constants.FAILED_STATUS, 'message': 'Suspicious file extension combination detected'}, status=400)

        # image_pattern = re.compile(r'^(?:\.jpg|\.jpeg|\.png|\.bmp|\.tiff|\.svg|\.webp|\.heic|\.heif)$', re.IGNORECASE)
        audio_pattern = re.compile(r'^(?:\.m4a|\.wav|\.mp3|\.mp4|\.wma|\.aac)$', re.IGNORECASE)
        # video_pattern = re.compile(r'^(?:\.mov|\.mp4|\.mkv|\.avi|\.wmv|\.flv|\.webm|\.mpeg|\.3gp|\.3g2|\.m4v)$', re.IGNORECASE)
        # document_pattern = re.compile(r'^(?:\.pdf|\.doc|\.docx|\.xls|\.xlsx|\.ppt|\.pptx|\.txt|\.csv)$', re.IGNORECASE)
        aws_keys = self.aws_initilization()
        waveform_data = None
        if audio_pattern.match(file_extension):
            try:
                if file_type.startswith("audio/"):
                    docType = 'Audio'
                    audio = AudioSegment.from_file(file_content, format=file_extension[1:])
                    output_file = f"{filename}.mp3"  # Convert to MP3
                    output_path = f"/tmp/{output_file}"
                    audio.export(output_path, format="mp3")
                    file_extension = '.mp3'
                    file_content = open(output_path, 'rb')
                    if is_recorded:
                        docType = 'RecordedAudio'
                    waveform_data = self.generate_waveform(output_path)
                else:
                    docType = 'Video'
                    # if not self.validate_magic_bytes(file_content, 'video'):
                        # return Response({'status': constants.response_constants.FAILED_STATUS, 'message': 'File content does not match video format'}, status=400)
            except:
                print(traceback.format_exc())
                docType = 'Video'
        else:
            return Response({'status': constants.FAILED_STATUS, 'message': 'Please record an audio'}, status=400)
        if docType == "Video":
            return Response({'status': constants.FAILED_STATUS, 'message': 'Please record an audio'}, status=400)
        current_time = datetime.now().strftime("%Y%m%d%H%M%S")
        new_file_name = f"{file_extension[1:]}_{current_time}{file_extension}"
        aws_bucket, aws_access_key_id, aws_secret_access_key, aws_region = self.aws_initilization()
        s3_client = boto3.client("s3", aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=aws_region)
        key = constants.AUDIO_REACTIONS + new_file_name
        existing_objects = s3_client.list_objects(Bucket=aws_bucket, Prefix=key).get('Contents', [])
        if existing_objects:
            raise Exception(f"File with name '{new_file_name}' already exists")
        # Initiate multipart upload
        multipart_upload = s3_client.create_multipart_upload(Bucket=aws_bucket, Key=key, ContentType=file_extension)
        parts = []
        part_number = 1
        chunk_size = 5 * 1024 * 1024  # 5 MB

        while True:
            # Read the next part
            data = file_content.read(chunk_size)
            if not data:
                break

            # Upload the part
            part = s3_client.upload_part(
                Bucket=aws_bucket,
                Key=key,
                PartNumber=part_number,
                UploadId=multipart_upload['UploadId'],
                Body=data
            )

            parts.append({'ETag': part['ETag'], 'PartNumber': part_number})
            part_number += 1

        # Complete multipart upload
        s3_client.complete_multipart_upload(
            Bucket=aws_bucket,
            Key=key,
            UploadId=multipart_upload['UploadId'],
            MultipartUpload={'Parts': parts}
        )
        reaction = Reactions.objects.create(
            question_id=question_id,
            user=user,
            voice_slug=new_file_name,
            waveform_data=waveform_data,
            parent_reaction=is_reaction
        )
        file_path = f"https://{aws_bucket}.s3.{aws_region}.amazonaws.com/{key}"
        return Response({"success": "Action successful", "data":aws_keys, "file_path":file_path}, status=status.HTTP_200_OK)



class S3UploadFiles(APIView):
    # permission_classes = (IsAuthenticated,)

    def get_aws_credentials(self):
        database = get_secret('REDIS_DB_0')
        redis_details_fetch = common.RedisDetailsFetch(database)
        config_key = "VENDOR_CONFIG_aws_s3"
        aws_config = redis_details_fetch.fetch_json_cred(config_key)
        return aws_config['AWS_BUCKET'], aws_config['AWS_ACCESS_KEY_ID'], aws_config['AWS_SECRET_ACCESS_KEY'], aws_config['REGION']

    def generate_presigned_url(self, url):
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.strip('/').split('/')
        directory = '/'.join(path_parts[:-1])
        filename = path_parts[-1]
        filename = unquote(filename)
        object_key = f"{directory}/{filename}"
        aws_bucket, aws_access_key_id, aws_secret_access_key, aws_region = self.get_aws_credentials()
        s3_client = boto3.client("s3", aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=aws_region)

        try:
            # Generate a pre-signed URL for the S3 object
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': aws_bucket, 'Key': object_key,
                        'ResponseContentDisposition': 'inline'}, # for making docs open in i frame
                ExpiresIn=3600
            )
            return url
        except Exception as e:
            print("Error generating pre-signed URL:", e)
            return None

    def is_valid_extension_combination(self, file_name):
        # Check for suspicious combinations like .php.png, .html.svg, etc.

        allowed_extensions = ['jpeg', 'jpg', 'png', 'bmp', 'tiff', 'svg', 'webp', 'heic', 'heif',
                            'm4a', 'wav', 'mp3', 'wma', 'aac', 'mp4', 'mov', 'mkv', 'avi', 'wmv',
                            'flv', 'webm', 'mpeg', '3gp', '3g2', 'm4v', 'pdf', 'doc', 'docx', 'xls',
                            'xlsx', 'ppt', 'pptx', 'txt', 'csv']

        base_filename, file_ext = os.path.splitext(file_name.lower())
        file_ext = file_ext[1:]
        if file_ext not in allowed_extensions:
            return True

        # Ensure the base filename doesn't end with a suspicious second extension
        last_dot_index = base_filename.rfind('.')
        if last_dot_index != -1:
            potential_extension = base_filename[last_dot_index + 1:]
            if potential_extension in allowed_extensions:
                return True

        return False


    def validate_magic_bytes(self, file_content, expected_type):
        # Validate file content based on magic bytes
        mime = magic.Magic(mime=True)
        mime_type = mime.from_buffer(file_content.read(2048))  # Read the first 2 KB for magic byte detection

        # Check if the mime type matches the expected type
        if expected_type in mime_type:
            return True
        return False

    def post(self, request):
        try:
            aws_bucket, aws_access_key_id, aws_secret_access_key, aws_region = self.get_aws_credentials()
            file_content = request.FILES.get('file_content')
            time_stamp = request.data.get('timeStamp', None)
            is_recorded = request.data.get("is_recorded")   # tag to identfy recorder audio

            if not file_content:
                return Response({'status': constants.response_constants.FAILED_STATUS, 'message': 'No file found'}, status=400)

            file_name = file_content.name
            file_type = file_content.content_type
            filename, file_extension = os.path.splitext(file_name)
            file_extension = file_extension.lower().strip()
            docType = 'Text'

            # Check for multiple extensions, e.g., .php.png, .svg.xlsx
            if self.is_valid_extension_combination(file_name):
                return Response({'status': constants.response_constants.FAILED_STATUS, 'message': 'Suspicious file extension combination detected'}, status=400)

            image_pattern = re.compile(r'^(?:\.jpg|\.jpeg|\.png|\.bmp|\.tiff|\.svg|\.webp|\.heic|\.heif)$', re.IGNORECASE)
            audio_pattern = re.compile(r'^(?:\.m4a|\.wav|\.mp3|\.wma|\.aac)$', re.IGNORECASE)
            video_pattern = re.compile(r'^(?:\.mov|\.mp4|\.mkv|\.avi|\.wmv|\.flv|\.webm|\.mpeg|\.3gp|\.3g2|\.m4v)$', re.IGNORECASE)
            document_pattern = re.compile(r'^(?:\.pdf|\.doc|\.docx|\.xls|\.xlsx|\.ppt|\.pptx|\.txt|\.csv)$', re.IGNORECASE)

            if image_pattern.match(file_extension):
                docType = 'Image'
                # if not self.validate_magic_bytes(file_content, 'image'):
                    # return Response({'status': constants.response_constants.FAILED_STATUS, 'message': 'File content does not match image format'}, status=400)
            elif document_pattern.match(file_extension):
                docType = 'Document'
                # if not self.validate_magic_bytes(file_content, 'document'):
                    # return Response({'status': constants.response_constants.FAILED_STATUS, 'message': 'File content does not match document format'}, status=400)
            elif audio_pattern.match(file_extension):
                docType = 'Audio'
                if is_recorded:
                    docType = 'RecordedAudio'
                # if not self.validate_magic_bytes(file_content, 'audio'):
                    # return Response({'status': constants.response_constants.FAILED_STATUS, 'message': 'File content does not match audio format'}, status=400)
            elif video_pattern.match(file_extension):
                try:
                    if file_type.startswith("audio/"):
                        docType = 'Audio'
                        audio = AudioSegment.from_file(file_content, format=file_extension[1:])
                        output_file = f"{filename}.mp3"  # Convert to MP3
                        output_path = f"/tmp/{output_file}"
                        audio.export(output_path, format="mp3")
                        file_extension = '.mp3'
                        file_content = open(output_path, 'rb')
                        if is_recorded:
                            docType = 'RecordedAudio'
                    else:
                        docType = 'Video'
                        # if not self.validate_magic_bytes(file_content, 'video'):
                            # return Response({'status': constants.response_constants.FAILED_STATUS, 'message': 'File content does not match video format'}, status=400)
                except:
                    print(traceback.format_exc())
                    docType = 'Video'
            elif file_extension == '.html':
                return Response({'status': constants.response_constants.FAILED_STATUS, 'message': 'HTML files are not allowed'}, status=400)

            # Sanitize file name and check allowed types
            current_time = datetime.now().strftime("%Y%m%d%H%M%S")
            if file_extension.lower() in ['.svg', '.heic', '.heif']:
                new_file_name = f"png_{current_time}.png"
            else:
                new_file_name = f"{file_extension[1:]}_{current_time}{file_extension}"
            allowed_types = ['.jpeg', '.jpg', '.png', '.bmp', '.tiff', '.svg', '.webp','.heic','.heif','.m4a', '.wav', '.mp3', '.wma', '.aac','.mp4', '.mov', '.mkv', '.avi', '.wmv', '.flv', '.webm', '.mpeg', '.3gp', '.3g2', '.m4v','.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt','.csv']
            if file_extension.lower() not in allowed_types:
                return Response({'status': constants.response_constants.FAILED_STATUS, 'message': 'Invalid file type'}, status=400)

            # Handle conversion for specific file types
            if file_extension.lower() in ['.svg', '.heic', '.heif']:
                try:
                    if file_extension.lower() == '.svg':
                        file_extension = '.png'
                        import cairosvg
                        svg_content = file_content.read()
                        png_output = BytesIO()

                        # Optimize SVG conversion with resolution limits
                        cairosvg.svg2png(
                            bytestring=svg_content,
                            write_to=png_output,
                            output_width=800,
                            output_height=600
                        )
                        png_output.seek(0)
                        converted_file = png_output

                    elif file_extension.lower() in ['.heic', '.heif']:
                        file_extension = '.png'

                        # Convert HEIC/HEIF to PNG with optimizations
                        heif_file = pyheif.read(file_content.read())
                        image = Image.frombytes(
                            heif_file.mode,
                            heif_file.size,
                            heif_file.data,
                            "raw",
                            heif_file.mode,
                            heif_file.stride,
                        )

                        # Resize the image to reduce size
                        max_width, max_height = 1024, 768
                        image.thumbnail((max_width, max_height))

                        # Save the image with compression
                        png_output = BytesIO()
                        image.save(png_output, format="PNG", optimize=True)
                        png_output.seek(0)
                        converted_file = png_output

                    # Replace file content with the converted PNG
                    file_content.file = converted_file
                    file_content.name = new_file_name
                    file_content.content_type = "image/png"

                except Exception as e:
                    print('FILE CONVERSION ERROR',traceback.format_exc())
                    return Response({'status': 'FAILED', 'message': f'File conversion failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

            # Upload file to S3
            s3_client = boto3.client("s3", aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=aws_region)
            key = constants.location.COMMUNICATIONDATA + new_file_name

            existing_objects = s3_client.list_objects(Bucket=aws_bucket, Prefix=key).get('Contents', [])
            if existing_objects:
                raise Exception(f"File with name '{new_file_name}' already exists")

            s3_client = boto3.client("s3", aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=aws_region)

            # Initiate multipart upload
            multipart_upload = s3_client.create_multipart_upload(Bucket=aws_bucket, Key=key, ContentType=file_extension)
            parts = []
            part_number = 1
            chunk_size = 5 * 1024 * 1024  # 5 MB

            while True:
                # Read the next part
                data = file_content.read(chunk_size)
                if not data:
                    break

                # Upload the part
                part = s3_client.upload_part(
                    Bucket=aws_bucket,
                    Key=key,
                    PartNumber=part_number,
                    UploadId=multipart_upload['UploadId'],
                    Body=data
                )

                parts.append({'ETag': part['ETag'], 'PartNumber': part_number})
                part_number += 1

            # Complete multipart upload
            s3_client.complete_multipart_upload(
                Bucket=aws_bucket,
                Key=key,
                UploadId=multipart_upload['UploadId'],
                MultipartUpload={'Parts': parts}
            )

            file_path = f"https://{aws_bucket}.s3.amazonaws.com/{key}"
            chatattachment_obj = ChatAttachment.objects.create(fileName=new_file_name, filePath=file_path, fileType=file_extension, docType=docType)
            lastchat_obj = ChatAttachment.objects.get(id=chatattachment_obj.id)
            externalID = request.data.get('app_user_id')
            chatType = request.data.get('chatType')

            # Handle chat related logic
            if externalID:
                fromid_Obj = CustomUser.objects.get(externalID=externalID)
            else:
                fromid_Obj = CustomUser.objects.get(id=request.data.get('sender_id'))
            sender_id = fromid_Obj.id
            chatRoomID = request.data.get('connectionID')
            members = queries.getGroupMembers(chatRoomID, "")
            reply_from_chat_id = request.data.get('replyFromChatID')

            # Logic for sending notifications and creating messages
            if chatType == 'Group':
                if reply_from_chat_id:
                    p2p_object = GroupChatMessage.objects.get(chatRoomID=chatRoomID, id=reply_from_chat_id)
                    count = p2p_object.replyCounter
                    if count:
                        count += 1
                        p2p_object.replyCounter = count
                        p2p_object.save()
                    else:
                        p2p_object.replyCounter = 1
                        p2p_object.save()
                else:
                    reply_from_chat_id = None
                GroupChatMessage.objects.create(
                    fromID=fromid_Obj,
                    chatRoomID=ChatRoom.objects.get(id=chatRoomID),
                    message="",
                    status=1,
                    isDeleted=0,
                    attachmentID=lastchat_obj,
                    replyFromChatID=reply_from_chat_id
                )
            else:
                if reply_from_chat_id:
                    p2p_object = P2PChatMessage.objects.get(chatRoomID=chatRoomID, id=reply_from_chat_id)
                    count = p2p_object.replyCounter
                    if count:
                        count += 1
                        p2p_object.replyCounter = count
                        p2p_object.save()
                    else:
                        p2p_object.replyCounter = 1
                        p2p_object.save()
                else:
                    reply_from_chat_id = None
                P2PChatMessage.objects.create(
                    fromID=fromid_Obj.id,
                    chatRoomID=ChatRoom.objects.get(id=chatRoomID),
                    message="",
                    status=1,
                    isDeleted=0,
                    attachmentID=lastchat_obj,
                    replyFromChatID=reply_from_chat_id
                )

            presigned_url = self.generate_presigned_url(file_path)

            # Send notifications to group members
            if members:
                for member in members:
                    if sender_id != member['id']:
                        message_type = docType
                        message = f"Attachment received {message_type}."
                        result = PNotifications.objects.create(communication_id=chatRoomID,
                                                    notification_title="New Attachment",
                                                    notification_text=message,
                                                    user_id=sender_id,
                                                    physician_user_id=member['id'],
                                                    read_status = 0,
                                                    sub_notification_type=message_type,
                                                    type = 1,
                                                    status = 1
                                                    )
                        result.save()

            return Response({
                'status': constants.response_constants.SUCCESS_STATUS,
                'message': 'File uploaded successfully',
                'file_path': presigned_url,
                'file_type': file_extension,
                'file_name': new_file_name,
                'docType': docType,
                'timeStamp': time_stamp
            }, status=200)

        except Exception as e:
            print(traceback.format_exc())
            return Response({'status': constants.response_constants.FAILED_STATUS, 'message': str(e)}, status=400)
            
