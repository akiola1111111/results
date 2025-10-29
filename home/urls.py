from django.urls import path
from . import views

urlpatterns = [
    # Authentication URLs
    path('', views.user_login, name='login'),
    path('logout/', views.custom_logout, name='logout'),
    path('signup/', views.teacher_signup, name='signup'),
    
    # Dashboard and Setup
    path('dashboard/', views.dashboard, name='dashboard'),
    path('quick-setup/', views.quick_setup, name='quick_setup'),
    
    # Class Management
    path('classes/', views.manage_classes, name='manage_classes'),
    path('class/<int:class_id>/', views.class_detail, name='class_detail'),
    path('class/<int:class_id>/results/', views.student_results_table, name='student_results_table'),
    path('class/<int:class_id>/report/', views.generate_report_card, name='class_report'),
    path('class/<int:class_id>/transcripts/', views.class_transcripts, name='class_transcripts'),
    
    # Score Management
    path('class/<int:class_id>/scores/', views.update_delete_scores, name='input_class_scores'),
    path('class/<int:class_id>/new-students/', views.new_student_scores, name='new_student_scores'),
    
    # Management Views
    path('manage/subjects/', views.manage_subjects, name='manage_subjects'),
    path('manage/terms/', views.manage_terms, name='manage_terms'),
    path('manage/assessments/', views.manage_assessments, name='manage_assessments'),
    path('manage/grading-config/', views.manage_grading_config, name='manage_grading_config'),
    
    # Transcripts - FIXED THE NAME HERE
    path('student/<int:student_id>/transcript/', views.generate_transcript, name='generate_transcript'),
    path('student/<int:student_id>/transcript/pdf/', views.generate_student_transcript_pdf, name='generate_student_transcript_pdf'),
    
    # Set current term
    path('set-current-term/<int:term_id>/', views.set_current_term, name='set_current_term'),
]