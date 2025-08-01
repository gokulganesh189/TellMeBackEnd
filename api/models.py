from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin,Group, Permission
from django.utils import timezone, text


class MStatus(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)
    
    class Meta:
        managed = True
        db_table = "m_status"
        indexes = [
            models.Index(fields=["name"]),
        ]
    
    
class MUserType(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)
    
    class Meta:
        managed = True
        db_table = "m_user_type"
        indexes = [
            models.Index(fields=["name"]),
        ]
    
def generate_username_from_email(email):
    if not email or '@' not in email:
        raise ValueError("Invalid email address")
    base_username = email.lower().split('@')[0]
    base_username = text.slugify(base_username)
    username = base_username
    counter = 1

    while CustomUser.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1

    return username
    
class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None,is_superuser=False, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        if not password:
            print('No password, setting pswd')
            password =""
            # raise ValueError("Users Must Have password")

        email = self.normalize_email(email)
        username = generate_username_from_email(email)
        user = self.model(email=email,username=username,is_superuser=is_superuser,**extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_staffuser(self,email,phone,name,countryCode,password=None,**extra_fields):
        user = self.create_user(email,phone=phone,name=name,countryCode=countryCode,password=password,is_staff=True,**extra_fields)
        return user
    
    def create_superuser(self,email,phone,name,countryCode,password=None,**extra_fields):
        user = self.create_user(email,phone=phone,name=name,countryCode=countryCode,password=password,is_staff=True,is_admin=True,**extra_fields)
        return user
    
class CustomUser(AbstractBaseUser, PermissionsMixin):
    groups = None  # This disables the built-in groups field
    user_permissions = None  # Disables user permissions field
    
    id = models.AutoField(primary_key=True)
    type = models.IntegerField(MUserType, default=4)
    username = models.CharField(max_length=255, null=True, blank=True,unique=True)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    countryCode = models.CharField(max_length=10, default='+1')
    country=models.IntegerField(db_column='country', null=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    isMobileNoVerified = models.BooleanField(default=False)
    is2FAEnabled = models.BooleanField(default=True)
    isNotificationEnabled = models.BooleanField(default=True)
    address = models.TextField(null=True, blank=True)
    status = models.ForeignKey(MStatus, on_delete=models.CASCADE, default=1)
    isVerified = models.BooleanField(default=0)
    changePwdOnLogin = models.IntegerField(default=0)
    password = models.CharField(max_length=255, null=True, blank=True)
    passwordResetSalt = models.CharField(max_length=100, null=True, blank=True)
    passwordResetFlag = models.BooleanField(null=True, blank=True)
    createDate = models.DateTimeField(auto_now=True)
    lastLoginTime = models.DateTimeField(null=True, blank=True)
    lastLoginIp = models.CharField(max_length=20, null=True, blank=True)
    profImage = models.CharField(max_length=50, null=True, blank=True)
    originalProfImage = models.CharField(max_length=255, null=True, blank=True,db_column='originalProfImage')

    last_login= models.DateTimeField(blank=True, null=True)
    is_superuser = models.BooleanField(default=False)
    # Fields required for authentication
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # Use the custom manager for user management
    objects = CustomUserManager()

    # Set the field that will be used for authentication (email in this case)
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []  # Add any other required fields
    
    groups = models.ManyToManyField(
        Group,
        verbose_name=('groups'),
        blank=True,
        related_name='customuser_set',  # Use a custom related_name
        related_query_name='user',
    )
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name=('user permissions'),
        blank=True,
        related_name='customuser_set',  # Use a custom related_name
        related_query_name='user',
    )

    class Meta:
        managed = True
        db_table = "app_users"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["username"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["status"]),
        ]
        unique_together = [("email",), ("username",)]
        
        
class DailyQuestions(models.Model):
    id = models.AutoField(primary_key=True)
    question = models.TextField()
    like_count = models.PositiveIntegerField(default=0)
    comment_count = models.PositiveIntegerField(default=0)
    status = models.ForeignKey(MStatus, on_delete=models.CASCADE, default=1)  # can be used to hide/archive
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, default=1)
    question_for = models.DateTimeField(null=False, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        managed = True
        db_table = "daily_questions"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]
        
class QuestionLike(models.Model):
    id = models.AutoField(primary_key=True)
    question = models.ForeignKey(DailyQuestions, on_delete=models.CASCADE, related_name='question_likes', default=1)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    status = models.ForeignKey(MStatus, on_delete=models.CASCADE, default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        managed = True
        db_table = "question_like"
        indexes = [
            models.Index(fields=["question"]),
            models.Index(fields=["status"]),
            models.Index(fields=["user"]),
            models.Index(fields=["created_at"]),
        ]
        
    
class Reactions(models.Model):
    id = models.AutoField(primary_key=True)
    question = models.ForeignKey(DailyQuestions, on_delete=models.CASCADE, related_name='reactions', default=1)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    status = models.ForeignKey(MStatus, on_delete=models.CASCADE, default=1)
    voice_slug = models.CharField(max_length=255)
    waveform_data = models.JSONField(blank=True, null=True)
    like_count = models.PositiveIntegerField(default=0)
    parent_reaction = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')  # This is used instead of `is_reply`
    transcript = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        managed = True
        db_table = "reaction"
        indexes = [
            models.Index(fields=["question"]),
            models.Index(fields=["user"]),
            models.Index(fields=["created_at"]),
        ]
        
class ReactionLike(models.Model):
    id = models.AutoField(primary_key=True)
    question = models.ForeignKey(DailyQuestions, on_delete=models.CASCADE, related_name='question_reaction_likes', default=1)
    reaction = models.ForeignKey(Reactions, on_delete=models.CASCADE, related_name='reaction_likes', default=1)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        managed = True
        db_table = "reaction_like"
        indexes = [
            models.Index(fields=["reaction"]),
            models.Index(fields=["question"]),
        ]

    
class UserStreak(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    current_streak = models.PositiveIntegerField(default=0)
    last_active = models.DateField(null=True, blank=True)
    
    class Meta:
        managed = True
        db_table = "user_streak"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["last_active"]),
        ]

    def update_streak(self, date=None):
        today = date or timezone.now().date()
        if self.last_active == today:
            return
        elif self.last_active == today - timezone.timedelta(days=1):
            self.current_streak += 1
        else:
            self.current_streak = 1
        self.last_active = today
        self.save()
        
        
class ExternalVendorConfig(models.Model):
    id = models.AutoField(primary_key=True)
    tag = models.CharField(max_length=255, null=True, blank=True)
    config_detail = models.JSONField()
    status = models.ForeignKey(MStatus, on_delete=models.CASCADE, default=1)
    update_date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        managed = True
        db_table = "external_vendor_config"
    
    