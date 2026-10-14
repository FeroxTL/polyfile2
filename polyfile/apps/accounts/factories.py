import factory

from polyfile.apps.accounts.models import User


class UserFactory(factory.django.DjangoModelFactory):
    """User factory."""
    class Meta:
        model = User
        django_get_or_create = ('username',)

    password = factory.django.Password("pw")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.Faker("email")
    username = factory.Faker("user_name")
