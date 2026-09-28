from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path("admin/login/", views.admin_login, name="admin_login"),
    path("admin/logout/", views.admin_logout, name="admin_logout"),
    path("", views.admin_home, name="admin_home"),

    # Users
    path("admin/users/", views.admin_view_normal_users, name="admin_view_normal_users"),

    # Players
    path("admin/players/", views.admin_view_players, name="admin_view_players"),
    path("admin/players/<int:player_id>/delete/", views.admin_delete_player, name="admin_delete_player"),

    # Clubs
    path("admin/clubs/", views.admin_view_clubs, name="admin_view_clubs"),
    path("admin/clubs/<int:club_id>/validate/", views.validate_club, name="validate_club"),
    path("admin/clubs/<int:club_id>/delete/", views.admin_delete_club, name="admin_delete_club"),

    # Turfs
    path("admin/turfs/", views.admin_view_turfs, name="admin_view_turfs"),
    path("admin/turfs/<int:turf_id>/validate/", views.validate_turf, name="validate_turf"),
    path("admin/turfs/<int:turf_id>/delete/", views.delete_turf, name="delete_turf"),

    # Matches
    path("admin/matches/", views.admin_view_matches, name="admin_view_matches"),
    path("admin/matches/<int:match_id>/", views.admin_view_match_detail, name="admin_match_detail"),
    path("admin/matches/<int:match_id>/delete/", views.admin_delete_match, name="admin_delete_match"),

    # Tournaments
    path("admin/tournaments/", views.admin_view_tournaments, name="admin_view_tournaments"),
    path("admin/tournaments/<int:t_id>/delete/", views.admin_delete_tournament, name="admin_delete_tournament"),

    # Time Schedules & Turf Time Maps
    path("admin/time-schedules/", views.admin_view_time_schedules, name="admin_view_time_schedules"),
    path("admin/turf-time-maps/", views.admin_view_turf_time_maps, name="admin_view_turf_time_maps"),

    # Bookings
    path("admin/bookings/", views.admin_view_bookings, name="admin_view_bookings"),
    path("admin/bookings/<int:booking_id>/update-status/", views.admin_update_booking_status, name="admin_update_booking_status"),

    # Payments
    path("admin/payments/", views.admin_view_payments, name="admin_view_payments"),

    # Notifications
    path("admin/notifications/", views.admin_view_notifications, name="admin_view_notifications"),
    path("admin/notifications/<int:notif_id>/mark-read/", views.admin_mark_notification_read, name="admin_mark_notification_read"),
    # Add these paths to your existing admin urlpatterns
    # Add these paths to your existing admin urlpatterns
    path('admin/tournaments/', views.admin_view_tournaments, name='admin_view_tournaments'),
    path('admin/tournaments/<int:t_id>/', views.admin_view_tournament_detail, name='admin_view_tournament_detail'),
    path('admin/tournaments/<int:t_id>/edit/', views.admin_edit_tournament, name='admin_edit_tournament'),
    path('admin/tournaments/<int:t_id>/delete/', views.admin_delete_tournament, name='admin_delete_tournament'),
    path('admin/tournaments/<int:t_id>/registrations/', views.admin_tournament_registrations, name='admin_tournament_registrations'),
    path('admin/tournaments/registrations/<int:t_c_id>/update/', views.admin_update_registration_status, name='admin_update_registration_status'),
    path('admin/tournaments/<int:t_id>/matches/', views.admin_tournament_matches, name='admin_tournament_matches'),
    path('admin/tournaments/matches/<int:match_id>/', views.admin_tournament_match_detail, name='admin_tournament_match_detail'),
    path('admin/tournaments/<int:t_id>/bracket/', views.admin_tournament_bracket, name='admin_tournament_bracket'),
    path('admin/tournaments/<int:t_id>/payments/', views.admin_tournament_payments, name='admin_tournament_payments'),
    path('admin/tournaments/matches/<int:match_id>/force-end/', views.admin_force_end_match, name='admin_force_end_match'),
    path('admin/tournaments/matches/<int:match_id>/update-score/', views.admin_update_match_score, name='admin_update_match_score'),
]
