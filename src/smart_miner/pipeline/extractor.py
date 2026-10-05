"""Provider-independent optional extraction and structural validation."""
from .document import CleanDocument


class StructuredExtractor:
    def __init__(self, generate, schema):
        """generate is an async callable receiving only cleaned source content.

        The callable returns JSON text or a dictionary. Schema validation does
        not verify factual accuracy or support for claims in the source.
        """
        self.generate = generate
        self.schema = schema

    async def extract(self, document: CleanDocument):
        if not isinstance(document, CleanDocument):
            raise TypeError("extract requires a CleanDocument")
        output = await self.generate(document.extraction_text())
        if isinstance(output, str):
            return self.schema.model_validate_json(output)
        return self.schema.model_validate(output)
