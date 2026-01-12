from django.urls import reverse_lazy
from django.views import generic
from .forms import StudentSignUpForm

class SignUpView(generic.CreateView):
    form_class = StudentSignUpForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'
