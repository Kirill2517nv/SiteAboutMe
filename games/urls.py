from django.urls import path
from . import views

app_name = 'games'

urlpatterns = [
    path('', views.games_landing_view, name='landing'),
    path('svoya-igra/', views.svoya_igra_list_view, name='si_list'),
    path('svoya-igra/pack/<int:pack_id>/', views.svoya_igra_pack_detail_view, name='si_pack_detail'),
    path('svoya-igra/pack/<int:pack_id>/play/', views.svoya_igra_play_view, name='si_play'),
    path('svoya-igra/create/', views.svoya_igra_create_view, name='si_create'),
    path('svoya-igra/my/', views.svoya_igra_my_view, name='si_my'),
    path('svoya-igra/moderate/', views.svoya_igra_moderate_list_view, name='si_moderate_list'),
    path('svoya-igra/moderate/<int:category_id>/', views.svoya_igra_moderate_detail_view, name='si_moderate_detail'),
    path('svoya-igra/packs/create/', views.svoya_igra_pack_create_view, name='si_pack_create'),
    path('svoya-igra/session/<int:session_id>/update/', views.svoya_igra_session_update_view, name='si_session_update'),
    path('svoya-igra/category/<int:category_id>/edit/', views.svoya_igra_category_edit_view, name='si_category_edit'),
    path('svoya-igra/question/<int:question_id>/edit/', views.svoya_igra_question_edit_view, name='si_question_edit'),
    path('svoya-igra/media/<int:media_id>/delete/', views.svoya_igra_media_delete_view, name='si_media_delete'),
    path('svoya-igra/my/<int:category_id>/edit/', views.svoya_igra_my_category_edit_view, name='si_my_edit'),
    path('svoya-igra/packs/manage/', views.svoya_igra_pack_manage_view, name='si_pack_manage'),
    path('svoya-igra/pack/<int:pack_id>/toggle-public/', views.svoya_igra_pack_toggle_public_view, name='si_pack_toggle_public'),
]
