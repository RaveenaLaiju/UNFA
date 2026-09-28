from django.urls import path
from django.conf.urls.static import static
from django.conf import settings
from . import views


urlpatterns = [
    # === PUBLIC / USER DASHBOARD ===
    path("", views.user_home, name="user_home"),
    path("user_logout", views.user_logout, name="user_logout"),

    # === PLAYERS ===
    path("user_players", views.view_players, name="user_players"),
    path("view_player_profile/<int:player_id>", views.view_player_profile, name="view_player_profile"),
    path("my_card", views.my_card, name="my_card"),
    path("register_player_card", views.register_player_card, name="register_player_card"),
    path("update_all_ratings", views.update_all_ratings, name="update_all_ratings"),
    path("player_public_profile/<int:player_id>/", views.player_public_profile, name="player_public_profile",),

    # === POSITIONS ===
    path("add_position", views.add_position, name="add_position"),

    # === MATCHES (Public viewing) ===
    path("watch_matches", views.watch_matches, name="watch_matches"),
    path("watch_live_score/<int:match_id>", views.watch_live_score, name="watch_live_score"),

    # === TURFS (Turf Owner) ===
    path("user_turfs", views.user_turfs, name="user_turfs"),
    path("turf_bookings/", views.turf_owner_home, name="turf_owner_home"),
    path("turf_booking_requests/", views.turf_booking_requests, name="turf_booking_requests"),
    path("register_turf", views.register_turf, name="register_turf"),
    path("update_turf/<int:turf_id>", views.update_turf, name="update_turf"),
    path("add_time_map/<int:turf_id>", views.add_time_map, name="add_time_map"),
    path("remove_time_map/<int:map_id>", views.remove_time_map, name="remove_time_map"),
    path("turf_payments/", views.turf_payments, name="turf_payments"),
    path("approve_booking/<int:booking_id>/", views.approve_booking, name="approve_booking"),
    path("reject_booking/<int:booking_id>/", views.reject_booking, name="reject_booking"),

    # === PAYMENTS ===
    path("initiate_payment/<int:booking_id>/", views.initiate_payment, name="initiate_payment"),
    path("payment_success/", views.payment_success, name="payment_success"),

    # === CLUBS ===
    path("user_clubs", views.user_clubs, name="user_clubs"),
    path("club_details/<int:club_id>", views.club_details, name="club_details"),
    path("search-clubs/", views.search_clubs, name="search_clubs"),
    path("register_club", views.register_club, name="register_club"),
    path("my_clubs", views.my_clubs, name="my_clubs"),
    path("quit_club", views.quit_club, name="quit_club"),
    path("club_update/<int:club_id>", views.club_update, name="club_update"),
    path("recruit_player/<int:club_id>/<int:player_id>", views.recruit_player, name="recruit_player"),
    path("remove_player/<int:player_id>", views.remove_player, name="remove_player"),
    path("club/<int:club_id>/remove-player/<int:player_id>/", views.remove_player_from_club, name="remove_player_from_club"),

    # === CLUB MANAGER DASHBOARD ===
    path("club_interface/<int:club_id>/", views.club_interface, name="club_interface"),
    path("check_match_requirement/<int:club_id>", views.check_match_requirement, name="check_match_requirement"),

    # === MATCH MANAGEMENT ===
    path("match_page", views.match_page, name="match_page"),
    path("get-available-slots/", views.get_available_slots, name="get_available_slots"),
    path("create_match", views.create_match, name="create_match"),
    path("club_matches", views.club_matches, name="club_matches"),
    path("cancel_match/<int:match_id>", views.cancel_match, name="cancel_match"),
    path("search_matches", views.search_matches, name="search_matches"),
    path("fix_match/<int:match_id>", views.fix_match, name="fix_match"),
    path("select_squad/<int:match_id>/<str:side>/", views.select_squad, name="select_squad"),
    path('simulate_payment/<int:booking_id>/', views.simulate_payment_success, name='simulate_payment'),

    # === MATCH LIVE ===
    path("go_to_match/<int:match_id>", views.go_to_match, name="go_to_match"),
    path("start_match/<int:match_id>", views.start_match, name="start_match"),
    path("match/<int:match_id>/pause/",views.pause_match,name="pause_match"),
    path("match/<int:match_id>/resume/",views.resume_match,name="resume_match"),
    path("end_match/<int:match_id>", views.end_match, name="end_match"),
    path('home_score_recorder/<int:match_id>/', views.home_score_recorder, name='home_score_recorder'),
    path('away_score_recorder/<int:match_id>/', views.away_score_recorder, name='away_score_recorder'),
    path("match_result/<int:match_id>/", views.match_result, name="match_result"),
    path("upload_video/<int:re_id>", views.upload_video, name="upload_video"),

    # === TOURNAMENTS ===
    path('tournaments/', views.tournament_list, name='tournament_list'),
    path('tournaments/host/', views.host_tournament, name='host_tournament'),
    path('tournaments/<int:t_id>/', views.view_tournament, name='view_tournament'),
    path('tournaments/<int:t_id>/join/', views.join_tournament, name='join_tournament'),
    path('tournaments/<int:t_id>/leave/', views.leave_tournament, name='leave_tournament'),
    path('tournaments/<int:t_id>/edit/', views.edit_tournament, name='edit_tournament'),
    path('tournaments/<int:t_id>/delete/', views.delete_tournament, name='delete_tournament'),
    path('tournaments/<int:t_id>/generate-fixtures/',views.generate_tournament_fixtures,name='generate_tournament_fixtures'),
    path('tournaments/<int:t_id>/update-stats/', views.update_tournament_stats, name='update_tournament_stats'),
    path('tournaments/<int:t_id>/bracket/', views.tournament_bracket, name='tournament_bracket'),
    path('matches/<int:match_id>/host-update-score/', views.host_update_score, name='host_update_score'),
    path('host_end_match/<int:match_id>/', views.host_end_match, name='host_end_match'),
    path('my-tournaments/',views.my_tournaments,name='my_tournaments'),

    # Tournament Payment URLs
    path('tournaments/<int:t_id>/payment/', views.tournament_payment_initiate, name='tournament_payment_initiate'),
    path('tournament/payment/success/<int:tp_id>/',views.tournament_payment_success, name='tournament_payment_success'),
    path('tournaments/<int:t_id>/payment/simulate/', views.simulate_tournament_payment, name='simulate_tournament_payment'),
    path('match/<int:match_id>/host-record-action/', views.host_record_action, name='host_record_action'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
