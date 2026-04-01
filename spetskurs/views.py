from django.shortcuts import render, get_object_or_404
from .models import TheoryPage, Simulation


def landing_view(request):
    theory_pages = TheoryPage.objects.filter(is_published=True).order_by('semester', 'order')
    simulations = Simulation.objects.filter(is_published=True).order_by('semester', 'order')[:3]
    context = {
        'theory_pages': theory_pages,
        'simulations': simulations,
        'active_section': 'landing',
    }
    return render(request, 'spetskurs/landing.html', context)


def theory_list_view(request):
    theory_pages = TheoryPage.objects.filter(is_published=True).order_by('semester', 'order')
    context = {
        'theory_pages': theory_pages,
        'active_section': 'theory',
    }
    return render(request, 'spetskurs/theory_list.html', context)


def theory_detail_view(request, slug):
    page = get_object_or_404(TheoryPage, slug=slug, is_published=True)
    blocks = page.blocks.all().order_by('order')

    all_pages = list(TheoryPage.objects.filter(is_published=True).order_by('semester', 'order'))
    idx = next((i for i, p in enumerate(all_pages) if p.pk == page.pk), None)
    prev_page = all_pages[idx - 1] if idx is not None and idx > 0 else None
    next_page = all_pages[idx + 1] if idx is not None and idx < len(all_pages) - 1 else None

    context = {
        'page': page,
        'blocks': blocks,
        'prev_page': prev_page,
        'next_page': next_page,
        'active_section': 'theory',
    }
    return render(request, 'spetskurs/theory_detail.html', context)


def simulation_list_view(request):
    simulations = Simulation.objects.filter(is_published=True).order_by('semester', 'order')
    context = {
        'simulations': simulations,
        'active_section': 'simulations',
    }
    return render(request, 'spetskurs/simulation_list.html', context)


def simulation_detail_view(request, slug):
    simulation = get_object_or_404(Simulation, slug=slug, is_published=True)
    context = {
        'simulation': simulation,
        'active_section': 'simulations',
    }
    return render(request, 'spetskurs/simulation_detail.html', context)
