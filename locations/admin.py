from django.contrib import admin

# Register your models here.
from django.contrib import admin

from locations.models import Pays

# Register your models here.
@admin.register(Pays)
class PaysAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code',)
    search_fields = ('name','code',)
    list_filter = ('code',)