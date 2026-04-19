from django import forms

from accounts.forms import style_form_fields

from .models import Announcement, Choice, Course, Question, QuestionType, Quiz, SemesterChoices


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = (
            'title',
            'subject_code',
            'summary',
            'description',
            'audience',
            'semester',
            'academic_year',
            'start_date',
            'end_date',
            'assessment_policy',
            'is_published',
        )
        labels = {
            'title': 'Название курса',
            'subject_code': 'Код дисциплины',
            'summary': 'Краткое описание',
            'description': 'Подробное описание',
            'audience': 'Целевая аудитория',
            'semester': 'Семестр',
            'academic_year': 'Учебный год',
            'start_date': 'Дата начала',
            'end_date': 'Дата завершения',
            'assessment_policy': 'Политика оценивания',
            'is_published': 'Опубликовать курс',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'assessment_policy': forms.Textarea(attrs={'rows': 4}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form_fields(self)


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = (
            'title',
            'description',
            'instructions',
            'time_limit_minutes',
            'passing_score',
            'max_attempts',
            'available_from',
            'available_until',
            'show_correct_answers',
            'is_published',
        )
        labels = {
            'title': 'Название теста',
            'description': 'Описание',
            'instructions': 'Инструкция для студентов',
            'time_limit_minutes': 'Лимит времени, мин.',
            'passing_score': 'Проходной балл, %',
            'max_attempts': 'Максимум попыток',
            'available_from': 'Доступен с',
            'available_until': 'Доступен до',
            'show_correct_answers': 'Показывать студенту правильные ответы после завершения',
            'is_published': 'Опубликовать тест',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'instructions': forms.Textarea(attrs={'rows': 4}),
            'available_from': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'available_until': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['available_from'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['available_until'].input_formats = ['%Y-%m-%dT%H:%M']
        style_form_fields(self)

    def clean(self):
        cleaned_data = super().clean()
        available_from = cleaned_data.get('available_from')
        available_until = cleaned_data.get('available_until')

        if available_from and available_until and available_until <= available_from:
            self.add_error('available_until', 'Дата окончания должна быть позже даты начала.')

        return cleaned_data


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ('text', 'topic', 'explanation', 'question_type', 'difficulty', 'points', 'order')
        labels = {
            'text': 'Текст вопроса',
            'topic': 'Тема',
            'explanation': 'Пояснение к правильному ответу',
            'question_type': 'Тип вопроса',
            'difficulty': 'Уровень сложности',
            'points': 'Баллы',
            'order': 'Порядок отображения',
        }
        widgets = {
            'text': forms.Textarea(attrs={'rows': 4}),
            'explanation': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form_fields(self)


class ChoiceForm(forms.ModelForm):
    class Meta:
        model = Choice
        fields = ('text', 'is_correct', 'order')
        labels = {
            'text': 'Текст варианта',
            'is_correct': 'Правильный вариант',
            'order': 'Порядок отображения',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form_fields(self)


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ('title', 'body', 'is_important')
        labels = {
            'title': 'Заголовок',
            'body': 'Текст объявления',
            'is_important': 'Пометить как важное',
        }
        widgets = {
            'body': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form_fields(self)


class JoinCourseForm(forms.Form):
    access_code = forms.CharField(label='Код курса', max_length=12)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form_fields(self)
        self.fields['access_code'].widget.attrs['placeholder'] = 'Например, AB12CD34'

    def clean_access_code(self):
        return self.cleaned_data['access_code'].strip().upper()


class CourseFilterForm(forms.Form):
    q = forms.CharField(label='Поиск', required=False)
    semester = forms.ChoiceField(
        label='Семестр',
        required=False,
        choices=[('', 'Все семестры'), *SemesterChoices.choices],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form_fields(self)


class AttemptForm(forms.Form):
    def __init__(self, *args, quiz, **kwargs):
        self.quiz = quiz
        super().__init__(*args, **kwargs)

        questions = quiz.questions.prefetch_related('choices').all()
        for question in questions:
            field_name = self.get_field_name(question.id)
            choices = [(str(choice.id), choice.text) for choice in question.choices.all()]

            if question.question_type == QuestionType.SINGLE:
                field = forms.ChoiceField(
                    label=question.text,
                    choices=choices,
                    widget=forms.RadioSelect,
                    required=False,
                )
            else:
                field = forms.MultipleChoiceField(
                    label=question.text,
                    choices=choices,
                    widget=forms.CheckboxSelectMultiple,
                    required=False,
                )

            field.question = question
            field.help_text = f'{question.get_difficulty_display()} • {question.points} балл(ов)'
            self.fields[field_name] = field

    @staticmethod
    def get_field_name(question_id):
        return f'question_{question_id}'

    def get_answers_mapping(self):
        answers = {}
        for question in self.quiz.questions.all():
            value = self.cleaned_data.get(self.get_field_name(question.id))
            if isinstance(value, list):
                answers[question.id] = {int(choice_id) for choice_id in value}
            elif value:
                answers[question.id] = {int(value)}
            else:
                answers[question.id] = set()
        return answers
