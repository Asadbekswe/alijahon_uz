from django.db.models import Model, SlugField, CharField, DateTimeField
from django.utils.text import slugify


class SlugBasedModel(Model):
    name = CharField(max_length=255)
    slug = SlugField(max_length=255, unique=True, editable=False)

    class Meta:
        abstract = True

    def _build_unique_slug(self):
        base = slugify(self.name, allow_unicode=True)[:240] or 'item'
        slug, index = base, 1
        siblings = self.__class__._default_manager.exclude(pk=self.pk)
        while siblings.filter(slug=slug).exists():
            index += 1
            slug = f'{base}-{index}'
        return slug

    def save(self, *args, **kwargs):
        # The slug is generated once; editing the name later must not break shared links.
        if not self.slug:
            self.slug = self._build_unique_slug()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class TimeBasedModel(Model):
    created_at = DateTimeField(auto_now_add=True, db_index=True)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SlugTimeBasedModel(TimeBasedModel, SlugBasedModel):
    class Meta:
        abstract = True
