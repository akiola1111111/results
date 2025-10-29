from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import *
from django.utils import timezone

class TeacherRegistrationForm(UserCreationForm):
    school_name = forms.CharField(max_length=200, required=True)
    school_address = forms.CharField(widget=forms.Textarea, required=True)
    school_phone = forms.CharField(max_length=15, required=True)
    school_email = forms.EmailField(required=False)
    school_logo = forms.ImageField(required=False)
    school_level = forms.ChoiceField(
        choices=[
            ('lower_primary', 'Lower Primary (P1-P3)'),
            ('upper_primary', 'Upper Primary (P4-P6)'),
            ('jhs', 'Junior High School (JHS)'),
            ('shs', 'Senior High School (SHS)'),
        ],
        required=True
    )
    phone = forms.CharField(max_length=15, required=True)

    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = 'teacher'
        
        # Create school
        school = School(
            name=self.cleaned_data['school_name'],
            address=self.cleaned_data['school_address'],
            phone=self.cleaned_data['school_phone'],
            email=self.cleaned_data['school_email'],
            school_level=self.cleaned_data['school_level']
        )
        if self.cleaned_data.get('school_logo'):
            school.logo = self.cleaned_data['school_logo']
        school.save()
        
        user.school = school
        if commit:
            user.save()
        
        # Create default grading configuration
        GradingConfiguration.objects.create(
            school=school,
            class_score_weight=50.00,
            exam_score_weight=50.00
        )
        
        return user

class QuickSetupForm(forms.Form):
    class_names = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'e.g., Primary 1, Primary 2, Primary 3'}),
        help_text="Enter class names separated by commas",
        required=True
    )
    subject_names = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'e.g., Mathematics, English, Science'}),
        help_text="Enter subject names separated by commas",
        required=True
    )
    
    # Add scaling configuration
    class_score_weight = forms.DecimalField(
        label="Class Score Weight (%)",
        min_value=0,
        max_value=100,
        initial=50.00,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
        help_text="What percentage should class assessments contribute to the final grade?"
    )
    exam_score_weight = forms.DecimalField(
        label="Exam Score Weight (%)", 
        min_value=0,
        max_value=100,
        initial=50.00,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
        help_text="What percentage should exams contribute to the final grade?"
    )
    
    term_name = forms.CharField(
        max_length=50, 
        initial=f"First Term {timezone.now().year}",
        required=True
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=True
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=True
    )
    
    def clean(self):
        cleaned_data = super().clean()
        class_weight = cleaned_data.get('class_score_weight')
        exam_weight = cleaned_data.get('exam_score_weight')
        
        if class_weight and exam_weight:
            total = float(class_weight) + float(exam_weight)
            if total != 100.00:
                raise forms.ValidationError(
                    f"Class score weight ({class_weight}%) and exam score weight ({exam_weight}%) must add up to 100%. "
                    f"Current total: {total}%"
                )
        return cleaned_data

class StudentRemarksForm(forms.ModelForm):
    class Meta:
        model = StudentRemarks
        fields = ['conduct', 'attitude', 'interest', 'class_teacher_remarks', 'total_attendance']
        widgets = {
            'class_teacher_remarks': forms.Textarea(attrs={'rows': 3}),
        }

class ClassForm(forms.ModelForm):
    class Meta:
        model = Class
        fields = ['name', 'teacher', 'level']

class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code']

class AcademicTermForm(forms.ModelForm):
    class Meta:
        model = AcademicTerm
        fields = ['name', 'start_date', 'end_date', 'is_current']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

class AssessmentTypeForm(forms.ModelForm):
    class Meta:
        model = AssessmentType
        fields = ['name', 'max_marks', 'weight', 'category']

class GradingConfigurationForm(forms.ModelForm):
    class Meta:
        model = GradingConfiguration
        fields = ['class_score_weight', 'exam_score_weight']
        widgets = {
            'class_score_weight': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'exam_score_weight': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        class_weight = cleaned_data.get('class_score_weight')
        exam_weight = cleaned_data.get('exam_score_weight')
        
        if class_weight and exam_weight:
            total = float(class_weight) + float(exam_weight)
            if total != 100.00:
                raise forms.ValidationError(
                    f"Class score weight ({class_weight}%) and exam score weight ({exam_weight}%) must add up to 100%. "
                    f"Current total: {total}%"
                )
        return cleaned_data