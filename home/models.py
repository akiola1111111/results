from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager
from django.utils import timezone

class CustomUserManager(UserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('user_type', 'teacher')
        return super().create_user(username, email, password, **extra_fields)
    
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('user_type', 'school_admin')
        return super().create_superuser(username, email, password, **extra_fields)

class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        ('school_admin', 'School Administrator'),
        ('teacher', 'Teacher'),
    )
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='teacher')
    school = models.ForeignKey('School', on_delete=models.CASCADE, null=True, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    
    objects = CustomUserManager()
    
    def __str__(self):
        return f"{self.username} ({self.get_user_type_display()})"

class School(models.Model):
    name = models.CharField(max_length=200)
    address = models.TextField()
    phone = models.CharField(max_length=15)
    email = models.EmailField(null=True)
    logo = models.ImageField(upload_to='school_logos/', null=True, blank=True)
    school_level = models.CharField(max_length=20, null=True, choices=[
        ('lower_primary', 'Lower Primary (P1-P3)'),
        ('upper_primary', 'Upper Primary (P4-P6)'), 
        ('jhs', 'Junior High School (JHS)'),
        ('shs', 'Senior High School (SHS)'),
    ])
    setup_completed = models.BooleanField(default=False)
   
    def __str__(self):
        return self.name

class AcademicTerm(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=50)  
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    is_current = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('school', 'name')
    
    def __str__(self):
        return f"{self.name}"

class Subject(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, blank=True)
    
    class Meta:
        unique_together = ('school', 'name')
    
    def __str__(self):
        return f"{self.name}"

class Class(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=50)
    teacher = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'user_type': 'teacher'})
    level = models.CharField(max_length=20, null=True, choices=[
        ('lower_primary', 'Lower Primary'),
        ('upper_primary', 'Upper Primary'),
        ('jhs', 'JHS'),
        ('shs', 'SHS'),
    ])
    
    class Meta:
        unique_together = ('school', 'name')
        verbose_name_plural = "Classes"
    
    def __str__(self):
        return f"{self.name}"

class Student(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)    
    current_class = models.ForeignKey(Class, on_delete=models.SET_NULL, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    parent_phone = models.CharField(max_length=15, blank=True)
    admission_number = models.CharField(max_length=20, null=True, unique=True)
    
    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} ({self.admission_number})"
    
    
class AssessmentType(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=100) 
    max_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100)  # Add this line
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    category = models.CharField(max_length=50, choices=[
        ('class_score', 'Class Score'), 
        ('exam', 'Exam')
    ], default='class_score')
    
    def __str__(self):
        return f"{self.name}"

class Score(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    assessment_type = models.ForeignKey(AssessmentType, on_delete=models.CASCADE)
    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    date_recorded = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('student', 'subject', 'assessment_type', 'term')
    
    def __str__(self):
        return f"{self.student} - {self.subject} - {self.score}"

class StudentRemarks(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='remarks')
    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE, related_name='student_remarks')
    conduct = models.CharField(max_length=100, default='Good')
    attitude = models.CharField(max_length=100, default='Positive')
    interest = models.CharField(max_length=100, default='High')
    class_teacher_remarks = models.TextField(default='N/A')
    total_attendance = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ('student', 'term')
    
    def __str__(self):
        return f"Remarks for {self.student.user.get_full_name()} ({self.term.name})"
    


    
class StudentTranscript(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='transcripts')
    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    class_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    exam_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    grade = models.CharField(max_length=2, default='N/A')
    remark = models.CharField(max_length=50, default='N/A')
    grade_point = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['student', 'term', 'subject']
    
    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.subject.name} ({self.term.name})"
    



class GradingConfiguration(models.Model):
    school = models.OneToOneField(School, on_delete=models.CASCADE)
    class_score_weight = models.DecimalField(max_digits=5, decimal_places=2, default=50.00)
    exam_score_weight = models.DecimalField(max_digits=5, decimal_places=2, default=50.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Grading config for {self.school.name}"
    
    def save(self, *args, **kwargs):
        # Ensure weights sum to 100
        total = float(self.class_score_weight) + float(self.exam_score_weight)
        if total != 100.00:
            raise ValueError("Class score and exam score weights must sum to 100%")
        super().save(*args, **kwargs)    