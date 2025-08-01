import boto3
from urllib.parse import urlparse
from urllib.parse import unquote
from api.models import ExternalVendorConfig


def get_external_credentials(tag):
    vendor_creds = ExternalVendorConfig.objects.get(tag=tag)
    if vendor_creds.config_detail:
        return {key: value for key, value in vendor_creds.config_detail.items()}
    else:
        return {}
        

def generate_presigned_url(self, url):
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip('/').split('/')
    directory = '/'.join(path_parts[:-1])
    filename = path_parts[-1]
    filename = unquote(filename)
    object_key = f"{directory}/{filename}"
    
    aws_bucket, aws_access_key_id, aws_secret_access_key, aws_region = self.get_external_credentials()
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
    
    "aws_s3"