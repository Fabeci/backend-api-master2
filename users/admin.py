from django.contrib import admin
from users.models import Admin, Apprenant, Formateur, Parent, ResponsableAcademique, User

# Register your models here.
@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('email', 'nom', 'prenom', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('email', 'nom', 'prenom')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'pays_residence')
    readonly_fields = ('date_joined',)


@admin.register(Admin)
class ApprenantAdmin(admin.ModelAdmin):
    list_display = ('email', 'nom', 'prenom', 'is_active')
    search_fields = ('email', 'nom', 'prenom')
    list_filter = ('is_active',)
    
       
@admin.register(ResponsableAcademique)
class ResponsableAcademiqueAdmin(admin.ModelAdmin):
    list_display = ('email', 'nom', 'prenom', 'is_active')
    search_fields = ('email', 'nom', 'prenom')
    list_filter = ('is_active',)


@admin.register(Formateur)
class FormateurAdmin(admin.ModelAdmin):
    list_display = ('email', 'nom', 'prenom', 'is_active')
    search_fields = ('email', 'nom', 'prenom')
    list_filter = ('is_active',)


@admin.register(Apprenant)
class ApprenantAdmin(admin.ModelAdmin):
    list_display = ('email', 'nom', 'prenom', 'is_active')
    search_fields = ('email', 'nom', 'prenom')
    list_filter = ('is_active',)


@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = ('email', 'nom', 'prenom', 'is_active')
    search_fields = ('email', 'nom', 'prenom')
    list_filter = ('is_active',)
