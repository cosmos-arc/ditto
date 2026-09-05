// SSE wire bodies are strings; this extension describes each JSON data field.
// Register it as a Schema node so standard reference and unused-component
// rules validate the payload contract without misrepresenting the wire body.
module.exports = {
  id: "ditto-sse",
  typeExtension: {
    oas3(types) {
      return {
        ...types,
        MediaType: {
          ...types.MediaType,
          properties: {
            ...types.MediaType.properties,
            "x-ditto-sse-data-schema": "Schema",
          },
        },
      };
    },
  },
};
