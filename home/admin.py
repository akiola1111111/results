from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, School, Class, Subject, Student, AcademicTerm, AssessmentType, Score, StudentRemarks, StudentTranscript

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'user_type', 'school', 'is_staff')
    list_filter = ('user_type', 'school', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('user_type', 'school', 'phone')}),
    )

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'school_level', 'phone', 'email')
    list_filter = ('school_level',)

@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'school', 'level', 'teacher')
    list_filter = ('school', 'level')

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'school')
    list_filter = ('school',)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('user', 'admission_number', 'current_class')
    list_filter = ('current_class__school', 'current_class')

@admin.register(AcademicTerm)
class AcademicTermAdmin(admin.ModelAdmin):
    list_display = ('name', 'school', 'start_date', 'end_date', 'is_current')
    list_filter = ('school', 'is_current')

@admin.register(AssessmentType)
class AssessmentTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'school', 'weight', 'category')
    list_filter = ('school', 'category')

@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'assessment_type', 'term', 'score')
    list_filter = ('term__school', 'term', 'subject')

@admin.register(StudentRemarks)
class StudentRemarksAdmin(admin.ModelAdmin):
    list_display = ('student', 'term', 'conduct', 'attitude')
    list_filter = ('term__school', 'term')

@admin.register(StudentTranscript)
class StudentTranscriptAdmin(admin.ModelAdmin):
    list_display = ('student', 'term', 'subject', 'total_score', 'grade', 'grade_point')
    list_filter = ('term__school', 'term', 'grade')
    search_fields = ('student__user__first_name', 'student__user__last_name', 'subject__name')