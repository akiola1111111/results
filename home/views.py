from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, F, Q
from django.db import transaction, IntegrityError
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone
import csv
from .models import *
from .forms import *
import uuid

# ========== NEW HELPER FUNCTIONS FOR DATA PRESERVATION ==========

def update_student_transcript(student, term, school):
    """Update transcript for a single student and term"""
    subjects = Subject.objects.filter(school=school)
    
    for subject in subjects:
        # Calculate scores using school's grading configuration
        score_calculation = calculate_subject_scores(student, subject, term, school)
        total_score = score_calculation['total_score']
        
        if total_score > 0:  # Only create transcript if there are scores
            school_level = school.school_level
            grade = get_grade(total_score, school_level)
            remark = get_remark(total_score, school_level)
            grade_point = get_grade_point(total_score, school_level)
            
            StudentTranscript.objects.update_or_create(
                student=student,
                term=term,
                subject=subject,
                defaults={
                    'class_score': score_calculation['class_score'],
                    'exam_score': score_calculation['exam_score'],
                    'total_score': total_score,
                    'grade': grade,
                    'remark': remark,
                    'grade_point': grade_point,
                }
            )

def archive_term_to_transcripts(term, school):
    """Archive all scores for a term to StudentTranscript records"""
    # Get all scores for this term
    scores = Score.objects.filter(
        term=term,
        student__current_class__school=school
    ).select_related('student', 'subject', 'term')
    
    students_processed = set()
    
    for score in scores:
        # Calculate the total score using school's grading configuration
        score_calculation = calculate_subject_scores(
            score.student, 
            score.subject, 
            term, 
            school
        )
        
        # Get Ghana grading system values
        school_level = school.school_level
        total_score = score_calculation['total_score']
        grade = get_grade(total_score, school_level)
        remark = get_remark(total_score, school_level)
        grade_point = get_grade_point(total_score, school_level)
        
        # Create or update transcript record
        StudentTranscript.objects.update_or_create(
            student=score.student,
            term=term,
            subject=score.subject,
            defaults={
                'class_score': score_calculation['class_score'],
                'exam_score': score_calculation['exam_score'],
                'total_score': total_score,
                'grade': grade,
                'remark': remark,
                'grade_point': grade_point,
            }
        )
        
        students_processed.add(score.student.id)
    
    return len(students_processed)

def archive_student_scores(student, term, school):
    """Archive all scores for a student to transcript before deletion or term change"""
    subjects = Subject.objects.filter(school=school)
    
    for subject in subjects:
        score_calculation = calculate_subject_scores(student, subject, term, school)
        total_score = score_calculation['total_score']
        
        if total_score > 0:
            school_level = school.school_level
            grade = get_grade(total_score, school_level)
            remark = get_remark(total_score, school_level)
            grade_point = get_grade_point(total_score, school_level)
            
            StudentTranscript.objects.update_or_create(
                student=student,
                term=term,
                subject=subject,
                defaults={
                    'class_score': score_calculation['class_score'],
                    'exam_score': score_calculation['exam_score'],
                    'total_score': total_score,
                    'grade': grade,
                    'remark': remark,
                    'grade_point': grade_point,
                }
            )

# ========== EXISTING HELPER FUNCTIONS ==========

def get_school_grading_config(school):
    """Get the grading configuration for a school"""
    try:
        return GradingConfiguration.objects.get(school=school)
    except GradingConfiguration.DoesNotExist:
        # Return default configuration (50/50)
        return type('DefaultConfig', (), {
            'class_score_weight': 50.00,
            'exam_score_weight': 50.00
        })()

def calculate_subject_scores(student, subject, term, school):
    """Calculate scores using school's grading configuration"""
    grading_config = get_school_grading_config(school)
    
    subject_scores = Score.objects.filter(student=student, subject=subject, term=term)
    
    class_assessments = subject_scores.filter(assessment_type__category='class_score')
    exam_assessment = subject_scores.filter(assessment_type__category='exam').first()

    # Calculate class score total and scale it
    class_score_total = sum(float(s.score) for s in class_assessments if s.score is not None)
    class_max_total = sum(float(a.assessment_type.max_marks) for a in class_assessments)
    
    if class_max_total > 0:
        scaled_class_score = (class_score_total / class_max_total) * float(grading_config.class_score_weight)
    else:
        scaled_class_score = 0

    # Calculate exam score and scale it
    exam_score = float(exam_assessment.score) if exam_assessment and exam_assessment.score is not None else 0
    exam_max_marks = float(exam_assessment.assessment_type.max_marks) if exam_assessment else 100
    
    if exam_max_marks > 0:
        scaled_exam_score = (exam_score / exam_max_marks) * float(grading_config.exam_score_weight)
    else:
        scaled_exam_score = 0

    subject_total = scaled_class_score + scaled_exam_score
    
    return {
        'class_score': round(scaled_class_score, 2),
        'exam_score': round(scaled_exam_score, 2),
        'total_score': round(subject_total, 2),
    }

# Ghana Grading System Helper Functions
def get_ghana_grading_system(school_level, score):
    """
    Ghana Education Service Grading System for different levels
    """
    try:
        score = float(score)
    except (TypeError, ValueError):
        return 6, 'No Score', 'F'
    
    if school_level in ['lower_primary', 'upper_primary']:
        # Primary School Grading (1-6 Scale)
        if score >= 90: return 1, 'Excellent', 'A+'
        elif score >= 80: return 1, 'Very Good', 'A'
        elif score >= 70: return 2, 'Good', 'B'
        elif score >= 60: return 3, 'Credit', 'C' 
        elif score >= 50: return 4, 'Pass', 'D'
        elif score >= 40: return 5, 'Weak', 'E'
        else: return 6, 'Very Weak', 'F'
    
    elif school_level == 'jhs':
        # JHS Grading System
        if score >= 80: return 1, 'Excellent', 'A'
        elif score >= 70: return 2, 'Very Good', 'B'
        elif score >= 60: return 3, 'Good', 'C'
        elif score >= 50: return 4, 'Credit', 'D'
        elif score >= 40: return 5, 'Pass', 'E'
        else: return 6, 'Fail', 'F'
    
    elif school_level == 'shs':
        # SHS/WASSCE Grading System
        if score >= 80: return 1, 'Excellent', 'A'
        elif score >= 75: return 1, 'Very Good', 'B+'
        elif score >= 70: return 2, 'Good', 'B'
        elif score >= 65: return 2, 'Credit', 'C+'
        elif score >= 60: return 3, 'Credit', 'C'
        elif score >= 55: return 3, 'Pass', 'D+'
        elif score >= 50: return 4, 'Pass', 'D'
        elif score >= 45: return 5, 'Weak', 'E'
        else: return 6, 'Fail', 'F'
    
    else:
        # Default grading
        if score >= 80: return 1, 'Excellent', 'A'
        elif score >= 70: return 2, 'Very Good', 'B'
        elif score >= 60: return 3, 'Good', 'C'
        elif score >= 50: return 4, 'Pass', 'D'
        elif score >= 40: return 5, 'Weak', 'E'
        else: return 6, 'Fail', 'F'

def get_remark(score, school_level):
    """Returns the appropriate remark based on score and school level"""
    _, remark, _ = get_ghana_grading_system(school_level, score)
    return remark

def get_grade(score, school_level):
    """Returns the grade based on score and school level"""
    _, _, grade = get_ghana_grading_system(school_level, score)
    return grade

def get_grade_point(score, school_level):
    """Returns the grade point based on score and school level"""
    grade_point, _, _ = get_ghana_grading_system(school_level, score)
    return grade_point

# ========== AUTHENTICATION VIEWS ==========

def teacher_signup(request):
    """Teacher registration with school creation"""
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        form = TeacherRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                user = form.save()
                
                # Log the user in
                login(request, user)
                messages.success(request, f'Account created successfully! Welcome to {user.school.name}.')
                return redirect('quick_setup')
            except Exception as e:
                messages.error(request, f'Error creating account: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = TeacherRegistrationForm()
    
    return render(request, 'signup.html', {'form': form})

def user_login(request):
    """Custom login view for teachers"""
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name}!')
                return redirect('dashboard')
        messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    
    return render(request, 'login.html', {'form': form})

def custom_logout(request):
    """Custom logout view that handles GET requests"""
    auth_logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('login')

# ========== UPDATED CORE VIEWS ==========

@login_required
def quick_setup(request):
    """Quick setup for new schools - PRESERVES existing data"""
    user_school = request.user.school
    
    # Check if user has a school
    if not user_school:
        messages.error(request, 'No school associated with your account.')
        return redirect('logout')
    
    # If setup is already completed, still allow access but show message
    if hasattr(user_school, 'setup_completed') and user_school.setup_completed:
        messages.info(request, 'You can modify your school setup here. Existing data will be preserved.')
    
    if request.method == 'POST':
        form = QuickSetupForm(request.POST)
        if form.is_valid():
            try:
                # PRESERVE EXISTING CLASSES - only create new ones
                class_names = [name.strip() for name in form.cleaned_data['class_names'].split(',') if name.strip()]
                existing_classes = Class.objects.filter(school=user_school)
                existing_class_names = [c.name for c in existing_classes]
                
                for class_name in class_names:
                    if class_name not in existing_class_names:
                        Class.objects.create(
                            school=user_school,
                            name=class_name,
                            level=user_school.school_level
                        )
                
                # PRESERVE EXISTING SUBJECTS - only create new ones
                subject_names = [name.strip() for name in form.cleaned_data['subject_names'].split(',') if name.strip()]
                existing_subjects = Subject.objects.filter(school=user_school)
                existing_subject_names = [s.name for s in existing_subjects]
                
                for subject_name in subject_names:
                    if subject_name not in existing_subject_names:
                        Subject.objects.create(
                            school=user_school,
                            name=subject_name,
                            code=subject_name[:3].upper()
                        )
                
                # PRESERVE ASSESSMENTS - only update weights, don't delete
                assessment_names = request.POST.getlist('assessment_names')
                assessment_weights = request.POST.getlist('assessment_weights')
                assessment_categories = request.POST.getlist('assessment_categories')
                
                # Update existing assessments or create new ones
                for name, weight, category in zip(assessment_names, assessment_weights, assessment_categories):
                    if name and weight:
                        AssessmentType.objects.update_or_create(
                            school=user_school,
                            name=name.strip(),
                            defaults={
                                'max_marks': weight,
                                'weight': weight,
                                'category': category
                            }
                        )
                
                # Update grading configuration
                grading_config, created = GradingConfiguration.objects.get_or_create(
                    school=user_school,
                    defaults={
                        'class_score_weight': form.cleaned_data['class_score_weight'],
                        'exam_score_weight': form.cleaned_data['exam_score_weight'],
                    }
                )
                
                if not created:
                    grading_config.class_score_weight = form.cleaned_data['class_score_weight']
                    grading_config.exam_score_weight = form.cleaned_data['exam_score_weight']
                    grading_config.save()
                
                # FIXED: Always set the new term as current when updating quick setup
                term_name = form.cleaned_data['term_name']
                
                # Unset all other current terms first
                AcademicTerm.objects.filter(school=user_school, is_current=True).update(is_current=False)
                
                # Create or update term and force it to be current
                term, created = AcademicTerm.objects.update_or_create(
                    school=user_school,
                    name=term_name,
                    defaults={
                        'start_date': form.cleaned_data['start_date'],
                        'end_date': form.cleaned_data['end_date'],
                        'is_current': True  # Always set as current
                    }
                )
                
                # Mark setup as completed
                user_school.setup_completed = True
                user_school.save()
                
                messages.success(request, f'School setup updated successfully! {term_name} is now the current term.')
                return redirect('dashboard')
                
            except Exception as e:
                messages.error(request, f'Error during setup: {str(e)}')
    else:
        # Pre-fill form with existing data or suggested values
        existing_classes = Class.objects.filter(school=user_school)
        existing_subjects = Subject.objects.filter(school=user_school)
        existing_assessments = AssessmentType.objects.filter(school=user_school)
        current_term = AcademicTerm.objects.filter(school=user_school, is_current=True).first()
        
        # Get existing grading config
        try:
            grading_config = GradingConfiguration.objects.get(school=user_school)
            class_weight = grading_config.class_score_weight
            exam_weight = grading_config.exam_score_weight
        except GradingConfiguration.DoesNotExist:
            class_weight = 50.00
            exam_weight = 50.00
        
        if existing_classes.exists() or existing_subjects.exists():
            # If we have existing data, pre-fill the form
            class_names = ', '.join([c.name for c in existing_classes])
            subject_names = ', '.join([s.name for s in existing_subjects])
        else:
            # Suggest classes based on school level
            if user_school.school_level == 'lower_primary':
                class_names = 'Primary 1, Primary 2, Primary 3'
                subject_names = 'Mathematics, English, Science, Creative Arts'
            elif user_school.school_level == 'upper_primary':
                class_names = 'Primary 4, Primary 5, Primary 6'
                subject_names = 'Mathematics, English, Science, Social Studies, Creative Arts'
            elif user_school.school_level == 'jhs':
                class_names = 'JHS 1, JHS 2, JHS 3'
                subject_names = 'Mathematics, English, Science, Social Studies, ICT, French'
            else:  # shs
                class_names = 'SHS 1, SHS 2, SHS 3'
                subject_names = 'Mathematics, English, Science, Social Studies, Elective Maths, Physics'
        
        initial_data = {
            'class_names': class_names,
            'subject_names': subject_names,
            'class_score_weight': class_weight,
            'exam_score_weight': exam_weight,
            'term_name': current_term.name if current_term else f'First Term {timezone.now().year}',
            'start_date': current_term.start_date if current_term else timezone.now().date(),
            'end_date': current_term.end_date if current_term else timezone.now().date() + timezone.timedelta(days=90),
        }
        
        form = QuickSetupForm(initial=initial_data)
    
    context = {
        'form': form,
        'school': user_school,
    }
    return render(request, 'quick_setup.html', context)

@login_required
def dashboard(request):
    user_school = request.user.school
    
    # Check if user has a school
    if not user_school:
        messages.error(request, 'No school associated with your account.')
        return redirect('logout')
    
    # For new users, redirect to quick setup
    if not hasattr(user_school, 'setup_completed') or not user_school.setup_completed:
        return redirect('quick_setup')
    
    # ALWAYS GET FRESH CURRENT TERM
    current_term = AcademicTerm.objects.filter(school=user_school, is_current=True).first()
    classes = Class.objects.filter(school=user_school)
    subjects = Subject.objects.filter(school=user_school)
    students_count = Student.objects.filter(current_class__school=user_school).count()
    
    context = {
        'current_term': current_term,
        'classes': classes,
        'subjects': subjects,
        'user_school': user_school,
        'students_count': students_count,
    }
    return render(request, 'dashboard.html', context)

@login_required
def class_detail(request, class_id):
    selected_class = get_object_or_404(Class, id=class_id, school=request.user.school)
    # ALWAYS GET FRESH CURRENT TERM
    current_term = AcademicTerm.objects.filter(school=request.user.school, is_current=True).first()
    students = Student.objects.filter(current_class=selected_class)

    context = {
        'selected_class': selected_class,
        'current_term': current_term,
        'students': students,
        'user_school': request.user.school,
    }
    return render(request, 'class_detail.html', context)

@login_required
def update_delete_scores(request, class_id):
    selected_class = get_object_or_404(Class, id=class_id, school=request.user.school)
    students = Student.objects.filter(current_class=selected_class).order_by('user__first_name')
    subjects = Subject.objects.filter(school=request.user.school).order_by('name')
    assessment_types = AssessmentType.objects.filter(school=request.user.school)
    # ALWAYS GET FRESH CURRENT TERM
    current_term = AcademicTerm.objects.filter(school=request.user.school, is_current=True).first()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        student_id_str = request.POST.get('student_id')
        
        if not student_id_str:
            messages.error(request, 'No student selected for this action.')
            return redirect('input_class_scores', class_id=class_id)
            
        student_id = int(student_id_str)
        student_to_modify = get_object_or_404(Student, id=student_id, current_class__school=request.user.school)
        
        if action == 'delete':          
            try:
                # ARCHIVE BEFORE DELETION: Save student scores to transcript
                if current_term:
                    archive_student_scores(student_to_modify, current_term, request.user.school)
                
                student_name = student_to_modify.user.get_full_name()
                student_to_modify.delete()
                messages.success(request, f'Successfully deleted {student_name}. Scores were archived to transcript.')
            except Exception as e:
                messages.error(request, f'Could not delete student. Error: {e}')
            return redirect('input_class_scores', class_id=class_id)
            
        elif action == 'update':
            if not current_term:
                messages.error(request, 'No current term is set. Cannot save scores.')
                return redirect('input_class_scores', class_id=class_id)
                
            success_count = 0
            for subject in subjects:
                for assessment in assessment_types:
                    field_name = f'score_{student_to_modify.id}_{subject.id}_{assessment.id}'
                    score_value = request.POST.get(field_name)
                    if score_value is not None and score_value != '':
                        try:
                            score_value = float(score_value)
                            Score.objects.update_or_create(
                                student=student_to_modify,
                                subject=subject,
                                assessment_type=assessment,
                                term=current_term,
                                defaults={'score': score_value}
                            )
                            success_count += 1
                        except (ValueError, TypeError):
                            messages.warning(request, f'Invalid score format for {student_to_modify.user.first_name}.')
            
            # AUTO-ARCHIVE: Update transcript when scores are saved
            if success_count > 0:
                update_student_transcript(student_to_modify, current_term, request.user.school)
                            
            messages.success(request, f'Successfully updated {success_count} scores for {student_to_modify.user.first_name}. Transcript updated automatically.')
            return redirect('input_class_scores', class_id=class_id)
    
    # Prepare scores data for display
    scores_data = {}
    if current_term:
        for student in students:
            scores_data[student.id] = {}
            for subject in subjects:
                scores_data[student.id][subject.id] = {}
                for assessment in assessment_types:
                    scores_data[student.id][subject.id][assessment.id] = None
        
        scores = Score.objects.filter(
            student__in=students, 
            term=current_term
        ).select_related('student', 'subject', 'assessment_type')
        
        for score in scores:
            student_id = score.student.id
            subject_id = score.subject.id
            assessment_type_id = score.assessment_type.id
            
            if student_id in scores_data and subject_id in scores_data[student_id]:
                scores_data[student_id][subject_id][assessment_type_id] = float(score.score)
    
    context = {
        'selected_class': selected_class,
        'current_term': current_term,
        'students': students,
        'subjects': subjects,
        'assessment_types': assessment_types,
        'scores_data': scores_data,
        'user_school': request.user.school,
    }
    return render(request, 'input_class_scores.html', context)

@login_required
def new_student_scores(request, class_id):
    selected_class = get_object_or_404(Class, id=class_id, school=request.user.school)
    subjects = Subject.objects.filter(school=request.user.school).order_by('name')
    assessment_types = AssessmentType.objects.filter(school=request.user.school)
    # ALWAYS GET FRESH CURRENT TERM
    current_term = AcademicTerm.objects.filter(school=request.user.school, is_current=True).first()

    if request.method == 'POST':
        if not current_term:
            messages.error(request, 'No current term is set. Cannot save scores.')
            return redirect('class_detail', class_id=class_id)
        
        post_data_keys = request.POST.keys()
        
        try:
            student_indices = sorted(list(set(int(key.split('_')[2]) for key in post_data_keys if key.startswith('student_name_'))))
        except (ValueError, IndexError):
            messages.error(request, 'Could not process student data. Please check form inputs.')
            return redirect('new_student_scores', class_id=class_id)
        
        total_scores_saved = 0
        students_added_count = 0
        
        for index in student_indices:
            full_name = request.POST.get(f'student_name_{index}')
            
            if not full_name:
                continue

            name_parts = full_name.split()
            first_name = name_parts[0] if len(name_parts) > 0 else 'New'
            last_name = name_parts[-1] if len(name_parts) > 1 else 'Student'
            
            try:
                # Generate truly unique identifiers
                timestamp = int(timezone.now().timestamp())
                unique_suffix = uuid.uuid4().hex[:6].upper()
                
                # Generate unique admission number
                admission_number = f"{first_name[0].upper()}{last_name[0].upper()}{timestamp % 10000:04d}{unique_suffix}"
                
                # Generate unique username
                username = f"student_{timestamp}_{unique_suffix.lower()}"
                
                # Create user for student - use transaction to ensure atomicity
                with transaction.atomic():
                    user = CustomUser.objects.create_user(
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        user_type='student',
                        school=request.user.school,
                        password='temp_password123'
                    )

                    # Create student
                    new_student = Student.objects.create(
                        user=user,
                        current_class=selected_class,
                        admission_number=admission_number,
                        date_of_birth='2000-01-01',
                        parent_phone='N/A'
                    )
                
                # Save scores outside transaction to avoid long locks
                scores_saved_for_student = 0
                for subject in subjects:
                    for assessment in assessment_types:
                        field_name = f'score_{index}_{subject.id}_{assessment.id}'
                        score_value = request.POST.get(field_name)
                        
                        if score_value and score_value.strip():
                            try:
                                score_value = float(score_value)
                                # Check if score already exists to avoid duplicates
                                if not Score.objects.filter(
                                    student=new_student,
                                    subject=subject,
                                    assessment_type=assessment,
                                    term=current_term
                                ).exists():
                                    Score.objects.create(
                                        student=new_student,
                                        subject=subject,
                                        assessment_type=assessment,
                                        term=current_term,
                                        score=score_value
                                    )
                                    scores_saved_for_student += 1
                            except (ValueError, TypeError) as e:
                                print(f"Invalid score value for {full_name}: {score_value} - {e}")
                                continue
                
                # AUTO-ARCHIVE: Update transcript for new student
                if scores_saved_for_student > 0:
                    update_student_transcript(new_student, current_term, request.user.school)
                    total_scores_saved += scores_saved_for_student
                    students_added_count += 1
                    
            except IntegrityError as e:
                print(f"IntegrityError for student {full_name}: {e}")
                if 'username' in str(e).lower():
                    messages.error(request, f'Username already exists for student: {full_name}. Please try again.')
                elif 'admission_number' in str(e).lower():
                    messages.error(request, f'Admission number already exists for student: {full_name}. Please try again.')
                else:
                    messages.error(request, f'Database error for student {full_name}. This might be a duplicate entry.')
                continue
                    
            except Exception as e:
                print(f"Unexpected error for student {full_name}: {e}")
                messages.error(request, f'Error creating student {full_name}: {str(e)}')
                continue
        
        if students_added_count > 0:
            messages.success(request, f'Successfully added {students_added_count} new student(s) and saved {total_scores_saved} scores. Transcripts updated automatically.')
            return redirect('student_results_table', class_id=selected_class.id)
        else:
            messages.warning(request, 'No valid student names or scores were provided. No data was saved.')
            return redirect('new_student_scores', class_id=class_id)

    context = {
        'selected_class': selected_class,
        'current_term': current_term,
        'subjects': subjects,
        'assessment_types': assessment_types,
        'user_school': request.user.school,
    }
    return render(request, 'new_student_scores.html', context)

@login_required
def student_results_table(request, class_id):
    selected_class = get_object_or_404(Class, id=class_id, school=request.user.school)
    # ALWAYS GET FRESH CURRENT TERM
    current_term = AcademicTerm.objects.filter(school=request.user.school, is_current=True).first()

    if not current_term:
        messages.error(request, 'No current term is set.')
        return redirect('class_detail', class_id=class_id)

    students = Student.objects.filter(current_class=selected_class).order_by('user__first_name')
    subjects = Subject.objects.filter(school=request.user.school).order_by('name')
    school_level = request.user.school.school_level

    results_data = []

    for student in students:
        student_data = {
            'student_obj': student,
            'name': student.user.get_full_name(),
            'admission_number': student.admission_number,
            'subject_data': {},
            'overall_total_score': 0,
            'overall_remark': '',
            'overall_grade': '',
            'overall_grade_point': 0,
        }

        for subject in subjects:
            # Use the new scoring calculation with school's grading configuration
            score_calculation = calculate_subject_scores(student, subject, current_term, request.user.school)
            
            subject_total = score_calculation['total_score']
            
            # Use Ghana grading system
            remark = get_remark(subject_total, school_level)
            grade = get_grade(subject_total, school_level)
            grade_point = get_grade_point(subject_total, school_level)

            student_data['subject_data'][subject.name] = {
                'class_score': score_calculation['class_score'],
                'exam_score': score_calculation['exam_score'],
                'total_score': subject_total,
                'grade': grade,
                'remark': remark,
                'grade_point': grade_point,
            }
            student_data['overall_total_score'] += subject_total
        
        student_data['overall_total_score'] = round(student_data['overall_total_score'], 2)
        
        # Calculate overall grade and remark
        average_score = student_data['overall_total_score'] / len(subjects) if subjects else 0
        student_data['overall_remark'] = get_remark(average_score, school_level)
        student_data['overall_grade'] = get_grade(average_score, school_level)
        student_data['overall_grade_point'] = get_grade_point(average_score, school_level)
        
        results_data.append(student_data)

    # Calculate positions
    for subject in subjects:
        results_data.sort(key=lambda x: x['subject_data'][subject.name]['total_score'], reverse=True)
        current_position = 1
        for i, student_data in enumerate(results_data):
            if i > 0 and student_data['subject_data'][subject.name]['total_score'] < results_data[i-1]['subject_data'][subject.name]['total_score']:
                current_position = i + 1
            student_data['subject_data'][subject.name]['position'] = current_position
            
    # Calculate overall positions
    results_data.sort(key=lambda x: x['overall_total_score'], reverse=True)
    current_position = 1
    for i, student_data in enumerate(results_data):
        if i > 0 and student_data['overall_total_score'] < results_data[i-1]['overall_total_score']:
            current_position = i + 1
        student_data['overall_position'] = current_position
    
    context = {
        'selected_class': selected_class,
        'current_term': current_term,
        'subjects': subjects,
        'results_data': results_data,
        'school_level': school_level,
        'user_school': request.user.school,
    }
    return render(request, 'student_results_table.html', context)

@login_required
def generate_report_card(request, class_id):
    """Generates a consolidated report card page for an entire class."""
    selected_class = get_object_or_404(Class, id=class_id, school=request.user.school)
    # ALWAYS GET FRESH CURRENT TERM
    current_term = AcademicTerm.objects.filter(school=request.user.school, is_current=True).first()

    if not current_term:
        messages.error(request, 'No current term is set.')
        return redirect('dashboard')

    students = Student.objects.filter(current_class=selected_class)
    school_level = request.user.school.school_level
    
    # Handle remarks submission
    if request.method == 'POST' and 'student_id' in request.POST:
        student_id = request.POST.get('student_id')
        try:
            student = Student.objects.get(id=student_id, current_class__school=request.user.school)
            
            # Get or create remarks for this student and term
            remarks, created = StudentRemarks.objects.get_or_create(
                student=student,
                term=current_term,
                defaults={
                    'conduct': 'Good',
                    'attitude': 'Positive',
                    'interest': 'High',
                    'class_teacher_remarks': 'N/A',
                    'total_attendance': 0
                }
            )
            
            form = StudentRemarksForm(request.POST, instance=remarks)
            if form.is_valid():
                form.save()
                messages.success(request, f'Remarks updated for {student.user.get_full_name()}')
                return redirect('generate_report_card', class_id=class_id)
            else:
                messages.error(request, 'Please correct the errors below.')
                
        except Student.DoesNotExist:
            messages.error(request, 'Student not found.')
        except Exception as e:
            messages.error(request, f'Error saving remarks: {str(e)}')
    
    # Get subjects
    subjects = Subject.objects.filter(school=request.user.school).order_by('name')
    
    if not subjects.exists():
        messages.warning(request, 'No subjects found for this school.')

    # Calculate totals for all students in the class
    all_class_totals = []
    for student in students:
        total_score = 0
        for subject in subjects:
            score_calculation = calculate_subject_scores(student, subject, current_term, request.user.school)
            total_score += score_calculation['total_score']
        all_class_totals.append({'student_id': student.id, 'total_score': total_score})

    all_class_totals.sort(key=lambda x: x['total_score'], reverse=True)
    
    results_data = []

    for student in students:
        # Get remarks for this student
        try:
            remarks_instance = StudentRemarks.objects.get(student=student, term=current_term)
            remarks_form = StudentRemarksForm(instance=remarks_instance)
        except StudentRemarks.DoesNotExist:
            remarks_form = StudentRemarksForm(initial={
                'conduct': 'Good',
                'attitude': 'Positive', 
                'interest': 'High',
                'class_teacher_remarks': 'N/A',
                'total_attendance': 0
            })
        
        student_data = {
            'id': student.id,
            'name': student.user.get_full_name(),
            'admission_number': student.admission_number,
            'subject_data': {},
            'overall_total_score': 0,
            'overall_average': 0,
            'overall_remark': '',
            'overall_grade': '',
            'overall_position': 0,
            'remarks_form': remarks_form,
        }

        for subject in subjects:
            subject_scores = Score.objects.filter(student=student, subject=subject, term=current_term)
            
            if not subject_scores.exists():
                student_data['subject_data'][subject.name] = {
                    'class_score': 0.0,
                    'exam_score': 0.0,
                    'total_score': 0.0,
                    'grade': 'N/A',
                    'remark': 'No Scores',
                    'grade_point': 0,
                }
                continue
            
            # Use the new scoring calculation with school's grading configuration
            score_calculation = calculate_subject_scores(student, subject, current_term, request.user.school)
            subject_total = score_calculation['total_score']
            
            # Use Ghana grading system
            remark = get_remark(subject_total, school_level)
            grade = get_grade(subject_total, school_level)
            grade_point = get_grade_point(subject_total, school_level)

            student_data['subject_data'][subject.name] = {
                'class_score': score_calculation['class_score'],
                'exam_score': score_calculation['exam_score'],
                'total_score': subject_total,
                'grade': grade,
                'remark': remark,
                'grade_point': grade_point,
            }
            student_data['overall_total_score'] += subject_total

        student_data['overall_total_score'] = round(student_data['overall_total_score'], 2)
        
        # Calculate average
        student_data['overall_average'] = round(student_data['overall_total_score'] / len(subjects), 2) if len(subjects) > 0 else 0

        # Set position
        for i, data in enumerate(all_class_totals):
            if data['student_id'] == student.id:
                student_data['overall_position'] = i + 1
                break
        
        # Calculate overall grade and remark using Ghana system
        student_data['overall_remark'] = get_remark(student_data['overall_average'], school_level)
        student_data['overall_grade'] = get_grade(student_data['overall_average'], school_level)

        results_data.append(student_data)

    context = {
        'results_data': results_data,
        'current_term': current_term,
        'selected_class': selected_class,
        'subjects_list': subjects,
        'total_students': students.count(),
        'school_info': request.user.school,
        'school_level': school_level,
        'user_school': request.user.school,
    }
    
    return render(request, 'card.html', context)

@login_required
def generate_transcript(request, student_id):
    """Generates a comprehensive transcript for a single student across all terms"""
    student = get_object_or_404(Student, id=student_id, current_class__school=request.user.school)
    school_level = request.user.school.school_level
    
    # Get all terms for this school, ordered by start date
    all_terms = AcademicTerm.objects.filter(school=request.user.school).order_by('-start_date', '-id')
    
    # Get transcript data from StudentTranscript model (archived data)
    transcript_records = StudentTranscript.objects.filter(
        student=student
    ).select_related('term', 'subject').order_by('term__start_date', 'subject__name')
    
    # Prepare transcript data from archived records
    transcript_data = {
        'student': student,
        'terms': [],
        'overall_summary': {
            'total_terms': all_terms.count(),
            'terms_with_data': 0,
            'overall_average': 0,
            'best_term': None,
            'best_score': 0,
        }
    }
    
    term_averages = []
    term_data_dict = {}
    
    # Group transcript records by term
    for record in transcript_records:
        term_id = record.term.id
        if term_id not in term_data_dict:
            term_data_dict[term_id] = {
                'term': record.term,
                'subjects': {},
                'term_total': 0,
                'term_average': 0,
                'subjects_count': 0
            }
        
        term_data_dict[term_id]['subjects'][record.subject.name] = {
            'class_score': float(record.class_score),
            'exam_score': float(record.exam_score),
            'total_score': float(record.total_score),
            'grade': record.grade,
            'remark': record.remark,
            'grade_point': record.grade_point,
        }
        
        term_data_dict[term_id]['term_total'] += float(record.total_score)
        term_data_dict[term_id]['subjects_count'] += 1
    
    # Calculate term averages and overall statistics
    for term_data in term_data_dict.values():
        if term_data['subjects_count'] > 0:
            term_data['term_average'] = round(term_data['term_total'] / term_data['subjects_count'], 2)
            term_averages.append(term_data['term_average'])
            transcript_data['overall_summary']['terms_with_data'] += 1
            
            # Update best term
            if term_data['term_average'] > transcript_data['overall_summary']['best_score']:
                transcript_data['overall_summary']['best_score'] = term_data['term_average']
                transcript_data['overall_summary']['best_term'] = term_data['term'].name
        
        transcript_data['terms'].append(term_data)
    
    # Calculate overall average
    if term_averages:
        transcript_data['overall_summary']['overall_average'] = round(
            sum(term_averages) / len(term_averages), 2
        )
    
    # Get all remarks for the student
    all_remarks = StudentRemarks.objects.filter(student=student).order_by('-term__start_date', '-term__id')

    context = {
        'transcript_data': transcript_data,
        'student': student,
        'school_info': request.user.school,
        'all_remarks': all_remarks,
        'school_level': school_level,
        'user_school': request.user.school,
    }
    
    return render(request, 'transcript.html', context)

@login_required  
def class_transcripts(request, class_id):
    """Shows all students in a class with links to their transcripts"""
    selected_class = get_object_or_404(Class, id=class_id, school=request.user.school)
    students = Student.objects.filter(current_class=selected_class).order_by('user__first_name')
    
    context = {
        'selected_class': selected_class,
        'students': students,
        'user_school': request.user.school,
    }
    
    return render(request, 'class_transcripts.html', context)

# ========== MANAGEMENT VIEWS ==========

@login_required
def manage_classes(request):
    """Manage classes for the school"""
    classes = Class.objects.filter(school=request.user.school)
    
    if request.method == 'POST':
        form = ClassForm(request.POST)
        if form.is_valid():
            class_obj = form.save(commit=False)
            class_obj.school = request.user.school
            class_obj.save()
            messages.success(request, f'Class {class_obj.name} created successfully!')
            return redirect('manage_classes')
    else:
        form = ClassForm()
    
    context = {
        'classes': classes,
        'form': form,
        'user_school': request.user.school,
    }
    return render(request, 'manage_classes.html', context)

@login_required
def manage_subjects(request):
    """Manage subjects for the school"""
    subjects = Subject.objects.filter(school=request.user.school)
    
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save(commit=False)
            subject.school = request.user.school
            subject.save()
            messages.success(request, f'Subject {subject.name} created successfully!')
            return redirect('manage_subjects')
    else:
        form = SubjectForm()
    
    context = {
        'subjects': subjects,
        'form': form,
        'user_school': request.user.school,
    }
    return render(request, 'manage_subjects.html', context)

@login_required
def manage_terms(request):
    """Manage academic terms for the school"""
    terms = AcademicTerm.objects.filter(school=request.user.school).order_by('-start_date')
    
    if request.method == 'POST':
        form = AcademicTermForm(request.POST)
        if form.is_valid():
            term = form.save(commit=False)
            term.school = request.user.school
            
            # If setting this as current, unset others
            if term.is_current:
                AcademicTerm.objects.filter(school=request.user.school, is_current=True).update(is_current=False)
            
            term.save()
            messages.success(request, f'Term {term.name} created successfully!')
            return redirect('manage_terms')
    else:
        form = AcademicTermForm()
    
    context = {
        'terms': terms,
        'form': form,
        'user_school': request.user.school,
    }
    return render(request, 'manage_terms.html', context)

@login_required
def set_current_term(request, term_id):
    """Set a term as current and archive previous term to transcripts"""
    new_term = get_object_or_404(AcademicTerm, id=term_id, school=request.user.school)
    old_current_term = AcademicTerm.objects.filter(school=request.user.school, is_current=True).first()
    
    try:
        with transaction.atomic():
            # Archive old term to transcripts if it exists and has scores
            if old_current_term and old_current_term.id != new_term.id:
                students_archived = archive_term_to_transcripts(old_current_term, request.user.school)
                if students_archived > 0:
                    messages.info(request, f'{old_current_term.name} results have been archived to transcripts for {students_archived} students.')
            
            # Unset all other current terms
            AcademicTerm.objects.filter(school=request.user.school, is_current=True).update(is_current=False)
            
            # Set new term as current
            new_term.is_current = True
            new_term.save()
            
            messages.success(request, f'{new_term.name} is now the current term.')
            
    except Exception as e:
        messages.error(request, f'Error switching terms: {str(e)}')
    
    return redirect('manage_terms')

@login_required
def manage_assessments(request):
    """Manage assessment types for the school"""
    assessments = AssessmentType.objects.filter(school=request.user.school)
    
    if request.method == 'POST':
        form = AssessmentTypeForm(request.POST)
        if form.is_valid():
            assessment = form.save(commit=False)
            assessment.school = request.user.school
            assessment.save()
            messages.success(request, f'Assessment {assessment.name} created successfully!')
            return redirect('manage_assessments')
    else:
        form = AssessmentTypeForm()
    
    context = {
        'assessments': assessments,
        'form': form,
        'user_school': request.user.school,
    }
    return render(request, 'manage_assessments.html', context)

@login_required
def manage_grading_config(request):
    """Manage grading configuration"""
    school = request.user.school
    
    try:
        grading_config = GradingConfiguration.objects.get(school=school)
    except GradingConfiguration.DoesNotExist:
        grading_config = GradingConfiguration.objects.create(
            school=school,
            class_score_weight=50.00,
            exam_score_weight=50.00
        )
    
    if request.method == 'POST':
        form = GradingConfigurationForm(request.POST, instance=grading_config)
        if form.is_valid():
            form.save()
            messages.success(request, 'Grading configuration updated successfully!')
            return redirect('manage_grading_config')
    else:
        form = GradingConfigurationForm(instance=grading_config)
    
    context = {
        'form': form,
        'grading_config': grading_config,
        'user_school': school,
    }
    return render(request, 'manage_grading_config.html', context)

@login_required  
def generate_student_transcript_pdf(request, student_id):
    """Generate PDF transcript for a student"""
    student = get_object_or_404(Student, id=student_id, current_class__school=request.user.school)
    
    # Get all terms and subjects for the student
    terms = AcademicTerm.objects.filter(school=request.user.school).order_by('start_date')
    subjects = Subject.objects.filter(score__student=student).distinct().order_by('name')
    
    # Prepare transcript data
    transcript_data = []
    school_level = request.user.school.school_level
    
    for term in terms:
        term_scores = Score.objects.filter(student=student, term=term)
        if not term_scores.exists():
            continue
            
        term_data = {
            'term': term,
            'subjects': {},
            'term_total': 0,
            'term_average': 0,
            'subjects_count': 0
        }
        
        for subject in subjects:
            subject_scores = term_scores.filter(subject=subject)
            if not subject_scores.exists():
                continue
                
            # Use the new scoring calculation
            score_calculation = calculate_subject_scores(student, subject, term, request.user.school)
            subject_total = score_calculation['total_score']
            
            remark = get_remark(subject_total, school_level)
            grade = get_grade(subject_total, school_level)
            grade_point = get_grade_point(subject_total, school_level)
            
            term_data['subjects'][subject.name] = {
                'total_score': subject_total,
                'grade': grade,
                'remark': remark,
                'grade_point': grade_point,
            }
            
            term_data['term_total'] += subject_total
            term_data['subjects_count'] += 1
        
        if term_data['subjects_count'] > 0:
            term_data['term_average'] = round(term_data['term_total'] / term_data['subjects_count'], 2)
            transcript_data.append(term_data)
    
    context = {
        'student': student,
        'transcript_data': transcript_data,
        'school_info': request.user.school,
        'school_level': school_level,
    }
    
    return render(request, 'transcript_pdf.html', context)
