from django.shortcuts import render

def home_page_view(request):
    return render(request, 'home.html')

def about_page_view(request):
    return render(request, 'about.html')
